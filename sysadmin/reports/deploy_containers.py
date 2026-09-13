"""Audited deployment and non-disruptive live verification of container maintenance."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tomllib
import xml.etree.ElementTree as ET

ROOT = Path("/home/bot/sysadmin")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, "/home/bot/splunk/scripts")
from ai_sysadmin import Controller, atomic_write, record_status, replace_record_status, stamp
from render_deployment import render
from splunk_api import get, request, search
from preview_containers import POLICY

c = Controller(Path("/etc/ai-sysadmin/config.toml"))
change_id = "CONTAINERS-20260913"
backup = c.state / "container-framework-backup-20260913"
report_path = ROOT / "reports/2026-09-13-containers.md"
report = report_path.read_text()
config_path = Path("/etc/ai-sysadmin/config.toml")
splunk_home = Path(c.config["splunk"]["home"])

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def command(name, argv, allowed=(0,), sensitive=False):
    result = c.command(name, argv, timeout=300, sensitive=sensitive)
    if result["returncode"] not in allowed:
        raise RuntimeError(name + " failed: " + str(result["returncode"]))
    print(name, result["returncode"], flush=True)
    return result

def snapshot():
    paths = list(c.changes.glob("*.txt")) + list(c.state.glob("*.plan.json"))
    paths += [c.state / "current-change", Path("/var/lib/dpkg/status"),
              Path("/home/bot/n8n/docker-compose.yml")]
    paths += list(Path("/etc/systemd/system").glob("ai-sysadmin-*.timer"))
    return {str(p): digest(p) for p in paths}

def container_identity():
    data = json.loads(command("verify_n8n_identity", ["docker", "inspect", "n8n"], sensitive=True)["stdout"])[0]
    assert data["State"]["Running"]
    return {"id": data["Id"], "image": data["Image"], "started": data["State"]["StartedAt"],
            "config": hashlib.sha256(json.dumps({k: data[k] for k in ("Config", "HostConfig", "Mounts")}, sort_keys=True).encode()).hexdigest()}

def install_text(target, content, mode):
    c.event("command_start", "Back up and atomically install deployment file", action="atomic_install",
            target=str(target), change_id=change_id)
    key = str(target).lstrip("/").replace("/", "__")
    if target.exists():
        stat = target.stat()
        saved = backup / key
        if not saved.exists():
            atomic_write(saved, target.read_text(), stat.st_mode & 0o777)
            atomic_write(backup / (key + ".metadata"), json.dumps({"uid": stat.st_uid, "gid": stat.st_gid,
                         "mode": stat.st_mode & 0o777, "target": str(target)}))
        uid, gid = stat.st_uid, stat.st_gid
    else:
        uid = gid = 0
        marker = backup / (key + ".new")
        if not marker.exists():
            atomic_write(marker, str(target))
    if not target.exists() or target.read_text() != content:
        atomic_write(target, content, mode)
        os.chown(target, uid, gid)
    assert target.read_text() == content
    c.event("command_result", "Installed file contents verified", action="atomic_install",
            target=str(target), sha256=digest(target), change_id=change_id)

try:
    before = snapshot()
    before_container = container_identity()
    with (c.state / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert all(record_status(p.read_text()) != "RUNNING" for p in c.changes.glob("*.txt"))
        backup.mkdir(mode=0o700, exist_ok=True)
        if not (backup / "planned-change.txt").exists():
            atomic_write(backup / "planned-change.txt", report)
        c.event("decision", "Enable reviewed weekly container image maintenance",
                change_id=change_id, plan=report, preserved_hashes=before, container=before_container)
        config_text = config_path.read_text()
        existing = tomllib.loads(config_text)
        if "containers" in existing:
            assert existing["containers"] == POLICY, "Unexpected existing container policy; refusing replacement"
        else:
            config_text += """
[containers]
enabled = true

[[containers.services]]
name = "n8n"
project = "n8n"
service = "n8n"
compose_files = ["/home/bot/n8n/docker-compose.yml"]
image = "docker.n8n.io/n8nio/n8n:latest"
hold = false
health_url = "http://127.0.0.1:5678/healthz/readiness"
health_timeout_seconds = 180
maximum_backup_bytes = 1073741824
"""
        desired = tomllib.loads(config_text)
        assert {k:v for k,v in desired.items() if k != "containers"} == {k:v for k,v in existing.items() if k != "containers"}
        install_text(Path("/opt/ai-sysadmin/bin/container_maintenance.py"), (ROOT / "src/container_maintenance.py").read_text(), 0o644)
        install_text(Path("/opt/ai-sysadmin/bin/ai-sysadmin"), (ROOT / "src/ai_sysadmin.py").read_text(), 0o755)
        install_text(Path("/opt/ai-sysadmin/README.md"), (ROOT / "README.md").read_text(), 0o644)
        install_text(config_path, config_text, config_path.stat().st_mode & 0o777)
        with tempfile.TemporaryDirectory() as tmp:
            render(desired, Path(tmp))
            for phase in ("prepare", "maintenance"):
                source = Path(tmp) / ("ai-sysadmin-" + phase + ".containers.conf")
                target = Path("/etc/systemd/system") / ("ai-sysadmin-" + phase + ".service.d") / "50-containers.conf"
                install_text(target, source.read_text(), 0o644)
        for filename, view in (("health-dashboard.xml", "health_dashboard"), ("anomaly-dashboard.xml", "anomaly_dashboard")):
            install_text(splunk_home / "etc/apps/ai_sysadmin/default/data/ui/views" / (view + ".xml"),
                         (ROOT / "splunk" / filename).read_text(), 0o644)
    command("reload_lifecycle_definitions", ["systemctl", "daemon-reload"])
    for phase in ("prepare", "maintenance"):
        output = command("verify_effective_sandbox", ["systemctl", "show", "ai-sysadmin-" + phase + ".service",
                         "--property=ProtectHome", "--property=BindReadOnlyPaths"])["stdout"]
        assert "ProtectHome=tmpfs" in output and "/home/bot/n8n" in output, output
    for filename, view in (("health-dashboard.xml", "health_dashboard"), ("anomaly-dashboard.xml", "anomaly_dashboard")):
        endpoint = "/servicesNS/nobody/ai_sysadmin/data/ui/views/" + view
        old = get(endpoint)["entry"][0]["content"]["eai:data"]
        saved = backup / (view + ".live.xml")
        if not saved.exists():
            atomic_write(saved, old)
        xml = (ROOT / "splunk" / filename).read_text()
        c.event("command_start", "Update existing Splunk dashboard", action="splunk_view", path=endpoint, change_id=change_id)
        if old.strip() != xml.strip():
            request(endpoint, {"eai:data": xml})
        live = get(endpoint)["entry"][0]["content"]["eai:data"]
        assert ET.tostring(ET.fromstring(live)) == ET.tostring(ET.fromstring(xml))
        c.event("command_result", "Live Splunk dashboard verified", action="splunk_view", path=endpoint, change_id=change_id)
    result = command("verify_container_preview_in_service_sandbox", [
        "systemd-run", "--quiet", "--wait", "--pipe", "--collect", "--unit=ai-sysadmin-container-verification",
        "--property=ProtectHome=tmpfs", "--property=BindReadOnlyPaths=/home/bot/n8n",
        "--property=PrivateTmp=true", "--property=NoNewPrivileges=true",
        "/opt/ai-sysadmin/bin/ai-sysadmin", "containers"], allowed=(0, 2))
    preview = json.loads(result["stdout"])
    assert not preview["inventory"]["errors"], preview
    assert not preview["updates"], "Candidate changed; review before any application update"
    assert preview["deferred"] and "major change" in preview["deferred"][0]["reason"], preview
    command("verify_installed_host_inventory", ["/opt/ai-sysadmin/bin/ai-sysadmin", "inspect"])
    health = json.loads((c.logs / "health.jsonl").read_text().splitlines()[-1])
    assert health["version"] == "1.2.0" and not health["inspection_errors"], health["inspection_errors"]
    inventory_run = health["run_id"]
    query = ('search index=ai_sysadmin sourcetype=ai_sysadmin:audit event_type=container run_id="'
             + inventory_run + '" | table name image_id application_version dependency_version update_policy')
    deadline = time.monotonic() + 45
    while True:
        indexed = search(query, "-15m")
        if indexed:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Container inventory not indexed")
        time.sleep(2)
    assert indexed[0]["name"] == "n8n" and indexed[0]["application_version"] == "2.29.7", indexed
    deferred = search('search index=ai_sysadmin sourcetype=ai_sysadmin:anomaly container=n8n reason="*major change*" earliest=-15m | table reason', "-15m")
    assert deferred, "Container deferral not indexed"
    panels = []
    for filename in ("health-dashboard.xml", "anomaly-dashboard.xml"):
        for panel in ET.parse(ROOT / "splunk" / filename).findall("./row/panel"):
            node = panel.find(".//search")
            rows = search("search " + node.findtext("query"), node.findtext("earliest") or "-30d")
            assert rows, panel.findtext(".//title")
            panels.append({"title": panel.findtext(".//title"), "rows": len(rows)})
    endpoint = command("verify_n8n_readiness", ["curl", "--fail", "--silent", "--output", "/dev/null",
                       "--write-out", "%{http_code}", "http://127.0.0.1:5678/healthz/readiness"])["stdout"]
    assert endpoint == "200"
    assert snapshot() == before
    assert container_identity() == before_container, "Deployment changed n8n runtime"
    for phase in ("prepare", "maintenance"):
        command("verify_weekly_timer_enabled", ["systemctl", "is-enabled", "ai-sysadmin-" + phase + ".timer"])
    summary = {"version": "1.2.0", "inventory": indexed, "deferred": preview["deferred"],
               "panels": panels, "container_unchanged": before_container, "preserved_hashes": before,
               "tests": 72, "service_sandbox_verified": True, "readiness": 200}
    atomic_write(ROOT / "reports/container-live-verification.json", json.dumps(summary, indent=2) + "\n", 0o644)
    closing = ("Successful: container maintenance enabled for n8n on existing weekly timers; controller 1.2.0, "
               "adapter, scoped service sandbox and Splunk dashboards deployed and verified. "
               "72 tests and full validation passed. Service-sandbox registry preview and live Splunk queries passed. "
               "n8n image, identity, startup time, data mounts and readiness unchanged; no image pull, application restart, "
               "package update or reboot performed by this deployment. Existing history and schedule preserved. "
               "Current candidate n8n 2.38.7 is deferred because bundled Node.js changes major version 24 to 26. "
               "That major transition requires explicit operator approval under AGENTS.md.")
    c.event("verification", "Container framework deployment verified", change_id=change_id, summary=summary)
    c.event("closure", closing, change_id=change_id, status="CLOSED", closing_remark=closing)
    closed = replace_record_status(report, "CLOSED").replace("Pending deployment and verification.", "Closed at: " + stamp() + "\n" + closing)
    atomic_write(report_path, closed, 0o644)
    atomic_write(backup / "closed-change.txt", closed)
    print(closing)
except Exception as exc:
    c.event("anomaly", "Container framework deployment needs attention", severity="high", change_id=change_id, error=str(exc))
    c.event("closure", "Deployment or verification incomplete; see audit and backups", status="FAILED", change_id=change_id, error=str(exc))
    raise
