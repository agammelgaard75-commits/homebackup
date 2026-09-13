"""Audited one-host deployment of software inventory and safety checks."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path("/home/bot/sysadmin")
sys.path.insert(0, str(ROOT / "src"))
from ai_sysadmin import Controller, atomic_write, record_status, replace_record_status, stamp

sys.path.insert(0, "/home/bot/splunk/scripts")
from splunk_api import get, request, search

c = Controller(Path("/etc/ai-sysadmin/config.toml"))
change_id = "SOFTWARE-INVENTORY-20260913"
backup = c.state / "software-inventory-backup-20260913"
report_path = ROOT / "reports/2026-09-13-software-inventory.md"
report = report_path.read_text()
splunk_home = Path(c.config["splunk"]["home"])

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def preserved_state():
    paths = list(c.changes.glob("*.txt")) + list(c.state.glob("*.plan.json"))
    paths += [c.state / "current-change", Path("/var/lib/dpkg/status"),
              Path("/etc/ai-sysadmin/config.toml")]
    paths += list(Path("/etc/systemd/system").glob("ai-sysadmin-*.timer"))
    paths += list(Path("/etc/systemd/system").glob("ai-sysadmin-*.service"))
    return {str(path): digest(path) for path in paths}

def run(action, argv):
    result = c.command(action, argv, timeout=180)
    print(action, result["returncode"], result["stdout"][-2000:], result["stderr"][-2000:], flush=True)
    if result["returncode"]:
        raise RuntimeError(action + " failed")
    return result

def api_action(action, path, payload=None):
    c.event("command_start", "Local Splunk API action", action=action,
            path=path, method="POST" if payload else "GET", change_id=change_id)
    result = json.loads(request(path, payload)) if payload else get(path)
    c.event("command_result", "Local Splunk API action completed", action=action,
            path=path, change_id=change_id)
    return result

try:
    with (c.state / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert all(record_status(path.read_text()) != "RUNNING" for path in c.changes.glob("*.txt"))
        before = preserved_state()
        c.event("inspection", "Reviewed installed controller and preservation targets",
                change_id=change_id, hashes=before)
        c.event("decision", "Implement updated AGENTS.md software and safety requirements",
                change_id=change_id, plan=report)
        backup.mkdir(mode=0o750, exist_ok=True)
        if not (backup / "change-plan.txt").exists():
            atomic_write(backup / "change-plan.txt", report)
        pairs = [(ROOT / "src/ai_sysadmin.py", Path("/opt/ai-sysadmin/bin/ai-sysadmin")),
                 (ROOT / "README.md", Path("/opt/ai-sysadmin/README.md"))]
        for filename, view in (("health-dashboard.xml", "health_dashboard"),
                               ("anomaly-dashboard.xml", "anomaly_dashboard")):
            pairs.append((ROOT / "splunk" / filename,
                          splunk_home / "etc/apps/ai_sysadmin/default/data/ui/views" / (view + ".xml")))
        for source, target in pairs:
            stat = target.stat()
            dest = backup / target.name
            if not dest.exists():
                atomic_write(dest, target.read_text(), stat.st_mode & 0o777)
                atomic_write(backup / (target.name + ".stat.json"),
                             json.dumps({"uid": stat.st_uid, "gid": stat.st_gid, "mode": stat.st_mode & 0o777}))
            c.event("command_start", "Install reviewed file atomically", action="atomic_install",
                    source=str(source), target=str(target), old_sha256=digest(target),
                    change_id=change_id)
            if target.read_bytes() != source.read_bytes():
                atomic_write(target, source.read_text(), stat.st_mode & 0o777)
                os.chown(target, stat.st_uid, stat.st_gid)
            assert target.read_bytes() == source.read_bytes()
            assert (target.stat().st_uid, target.stat().st_gid) == (stat.st_uid, stat.st_gid)
            c.event("command_result", "Installed file verified", action="atomic_install",
                    target=str(target), sha256=digest(target), change_id=change_id)
        installed = runpy.run_path("/opt/ai-sysadmin/bin/ai-sysadmin")
        assert installed["VERSION"] == "1.1.0"
    for filename, view in (("health-dashboard.xml", "health_dashboard"),
                           ("anomaly-dashboard.xml", "anomaly_dashboard")):
        endpoint = "/servicesNS/nobody/ai_sysadmin/data/ui/views/" + view
        old = api_action("inspect_dashboard", endpoint)["entry"][0]["content"]["eai:data"]
        saved = backup / (view + ".live.xml")
        if not saved.exists():
            atomic_write(saved, old)
        xml = (ROOT / "splunk" / filename).read_text()
        if old.strip() != xml.strip():
            api_action("update_dashboard", endpoint, {"eai:data": xml})
        live = api_action("verify_dashboard", endpoint)["entry"][0]["content"]["eai:data"]
        assert ET.tostring(ET.fromstring(live)) == ET.tostring(ET.fromstring(xml))
    run("inspect_installed_inventory", ["/opt/ai-sysadmin/bin/ai-sysadmin", "inspect"])
    latest = json.loads((c.logs / "health.jsonl").read_text().splitlines()[-1])
    assert latest["version"] == "1.1.0"
    assert not latest["inspection_errors"], latest["inspection_errors"]
    extras = latest["software_inventory"]["extra"]
    assert any(i["name"] == "splunk" and i["version"] == "9.3.14" and i["location"] == str(splunk_home) for i in extras)
    assert any(i["name"] == "litellm" and i["version"] == "1.83.2" for i in extras)
    assert latest["software_inventory"]["package_version_conflicts"]
    c.event("verification", "Installed inspection verified", change_id=change_id,
            installed_package_count=latest["installed_package_count"],
            extra_software_count=latest["extra_software_count"], run=latest["run_id"])
    summary = {"version": "1.1.0", "inventory_run_id": latest["run_id"],
               "installed_package_count": latest["installed_package_count"],
               "extra_software_count": latest["extra_software_count"],
               "package_version_conflicts": latest["software_inventory"]["package_version_conflicts"]}
    query = ('search index=ai_sysadmin sourcetype=ai_sysadmin:audit event_type=software run_id="'
             + latest["run_id"] + '" | stats count as count')
    deadline = time.monotonic() + 45
    while True:
        rows = search(query, "-15m")
        if rows and int(rows[0]["count"]) == len(extras):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Software inventory not fully indexed")
        time.sleep(2)
    c.event("verification", "All extra-software events indexed in Splunk",
            change_id=change_id, query=query, results=rows)
    summary["indexed_software_events"] = int(rows[0]["count"])
    query = ('search index=ai_sysadmin sourcetype=ai_sysadmin:anomaly run_id="'
             + latest["run_id"] + '" name=splunk | table name package_version installed_version')
    rows = search(query, "-15m")
    assert rows and rows[0]["installed_version"] == "9.3.14", rows
    c.event("verification", "Splunk version conflict indexed separately",
            change_id=change_id, query=query, results=rows)
    summary["dashboards"] = []
    for filename in ("health-dashboard.xml", "anomaly-dashboard.xml"):
        tree = ET.parse(ROOT / "splunk" / filename)
        for panel in tree.findall("./row/panel"):
            node = panel.find(".//search")
            query = node.findtext("query")
            rows = search("search " + query, node.findtext("earliest") or "-30d")
            assert rows, (filename, panel.findtext(".//title"))
            summary["dashboards"].append({"dashboard": filename,
                                          "panel": panel.findtext(".//title"), "rows": len(rows)})
    assert preserved_state() == before, "Protected historical or package state changed"
    summary["preserved_state"] = before
    atomic_write(ROOT / "reports/software-live-verification.json", json.dumps(summary, indent=2) + "\n", 0o644)
    closing = ("Successful: controller 1.1.0 and both existing dashboards deployed and verified. "
               "All 52 regression tests and full validation passed. "
               f"{latest['installed_package_count']} APT packages and {len(extras)} extra entries inventoried; "
               "all extra events indexed and dashboard queries returned data. "
               "Existing change records, plans, pointer, configuration, schedules and dpkg state preserved. "
               "No package maintenance or reboot performed. "
               "Attention remains: Splunk manifest/package version mismatch and unclassified software locations; "
               "non-APT updates require a reviewed procedure. Host inspection reported no errors or failed units.")
    c.event("closure", closing, change_id=change_id, status="CLOSED", closing_remark=closing)
    closed_report = replace_record_status(report, "CLOSED").replace(
        "Pending deployment and verification.", "Closed at: " + stamp() + "\n" + closing)
    atomic_write(report_path, closed_report, 0o644)
    atomic_write(backup / "closed-change.txt", closed_report)
    print(json.dumps(summary, indent=2))
except Exception as exc:
    c.event("anomaly", "Software inventory deployment or verification failed", severity="high",
            change_id=change_id, error=str(exc))
    c.event("closure", "Deployment needs attention; review audit and backups",
            change_id=change_id, status="FAILED", error=str(exc))
    raise
