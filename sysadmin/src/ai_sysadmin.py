#!/usr/bin/env python3
"""Conservative, auditable Ubuntu weekly maintenance controller."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any

from container_maintenance import ContainerMaintenance

VERSION = "1.3.0"
CHANGE_ID_PATTERN = r"CHG-\d{8}(?:-R[1-9]\d*)?"
DEFAULT_CONFIG = Path("/etc/ai-sysadmin/config.toml")


def software_name(name: str) -> str:
    return name.split(":", 1)[0].lower()


def read_ignore_file(path: Path) -> dict[str, dict[str, str]]:
    """Read strict Markdown bullets: '- software-name: operator reason'."""
    if not path.exists():
        return {}
    metadata = path.stat()
    if path.is_symlink() or not path.is_file() or metadata.st_size > 65536 or metadata.st_mode & 0o022:
        raise ValueError("IGNORE.md must be a non-writable regular file no larger than 64 KiB")
    ignored = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"- ([A-Za-z0-9][A-Za-z0-9+._-]*): (\S.{0,499})", line)
        if not match:
            raise ValueError(f"Invalid IGNORE.md entry on line {number}")
        name, reason = match.groups()
        key = name.lower()
        if key in ignored:
            raise ValueError(f"Duplicate IGNORE.md entry for {name}")
        ignored[key] = {"name": name, "reason": reason, "line": str(number)}
    return ignored


def upgrade_candidates(output: str, ignored: set[str] | None = None) -> tuple[list[dict[str, str]], list[str]]:
    """Fail closed on removals, new installs and ambiguous/major transitions."""
    packages, errors = [], []
    for line in output.splitlines():
        if line.startswith(("Remv ", "Purg ")):
            errors.append("Package removal prohibited: " + line)
        elif line.startswith("Inst "):
            match = re.match(r"Inst ([a-z0-9][a-z0-9+.:~-]*) \[([^\]]+)\] \(([^\s)]+)", line)
            if not match:
                errors.append("New install or unrecognized upgrade requires review: " + line)
                continue
            name, old, new = match.groups()
            if software_name(name) in (ignored or set()):
                continue

            def series(version: str) -> tuple[str, str] | None:
                epoch, upstream = version.split(":", 1) if ":" in version else ("0", version)
                major = re.match(r"(\d+)\.", upstream)
                return (epoch, major[1]) if major else None

            old_upstream, new_upstream = old.rsplit("-", 1)[0], new.rsplit("-", 1)[0]
            if old_upstream != new_upstream and (series(old) is None or series(old) != series(new)):
                errors.append(f"Major or unclassified version change requires review: {name} {old} -> {new}")
            packages.append({"name": name, "before": old, "after": new})
    return packages, errors


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def stamp() -> str:
    return utcnow().isoformat(timespec="seconds")


def record_status(text: str) -> str:
    """Read the single status field in the header, never prose in the body."""
    header, separator, _ = text.partition("\n\n")
    fields = [line for line in header.splitlines() if line.startswith("Status:")]
    if not separator or len(fields) != 1:
        raise ValueError("Change header must have exactly one status field")
    match = re.fullmatch(r"Status: (PREPARED|RUNNING|CLOSED|FAILED)", fields[0])
    if not match:
        raise ValueError("Invalid change status")
    return match.group(1)


def replace_record_status(text: str, status: str) -> str:
    current = record_status(text)
    header, separator, body = text.partition("\n\n")
    header = re.sub(r"^Status: " + current + r"$", "Status: " + status,
                    header, count=1, flags=re.MULTILINE)
    return header + separator + body


def atomic_write(path: Path, content: str, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Controller:
    write = staticmethod(atomic_write)

    def __init__(self, config_path: Path, dry_run: bool = False) -> None:
        self.config_path = config_path.resolve()
        with config_path.open("rb") as handle:
            self.config = tomllib.load(handle)
        self.dry_run = dry_run
        self.state = Path(self.config["paths"]["state_dir"])
        self.logs = Path(self.config["paths"]["log_dir"])
        if dry_run:
            # Keep plans, pointers, locks and logs separate even with live config.
            self.state = self.state / "dry-run"
            self.logs = self.logs / "dry-run"
        self.changes = self.state / "changes"
        self.state.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.changes.mkdir(parents=True, exist_ok=True)
        self.run_id = f"{utcnow():%Y%m%dT%H%M%SZ}-{os.getpid()}"
        self.ignore_file = Path(self.config.get("paths", {}).get("ignore_file", "/etc/ai-sysadmin/IGNORE.md"))
        self.ignore_errors = []
        try:
            self.ignored = read_ignore_file(self.ignore_file)
        except (OSError, UnicodeError, ValueError) as exc:
            self.ignored = {}
            self.ignore_errors.append(str(exc))
        normalized = {key: value["reason"] for key, value in sorted(self.ignored.items())}
        self.ignore_policy_sha256 = hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()
        self.containers = ContainerMaintenance(self)

    def event(self, event_type: str, message: str, **fields: Any) -> None:
        record = {
            "timestamp": stamp(), "host": socket.gethostname(),
            "run_id": self.run_id, "event_type": event_type,
            "message": message, "version": VERSION, "dry_run": self.dry_run, **fields,
        }
        if event_type in ("phase", "ai_request", "ai_response", "change", "closure"):
            print(f"[{record['timestamp']}] {message}", file=sys.stderr, flush=True)
        target = "audit.jsonl"
        if event_type == "health":
            target = "health.jsonl"
        elif event_type == "anomaly":
            target = "anomalies.jsonl"
        elif event_type == "ignored":
            target = "ignored.jsonl"
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        path = self.logs / target
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line.encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def command(self, action: str, argv: list[str], timeout: int = 60,
                mutate: bool = False, sensitive: bool = False) -> dict[str, Any]:
        safe_argv = list(argv)
        self.event("command_start", "Executing approved action", action=action,
                   argv=safe_argv, mutating=mutate, dry_run=self.dry_run)
        if mutate and self.dry_run:
            result = {"returncode": 0, "stdout": "dry-run: skipped", "stderr": "",
                      "duration_seconds": 0.0}
            self.event("command_result", "Action skipped in dry-run", action=action, **result)
            return result
        started = time.monotonic()
        try:
            proc = subprocess.run(safe_argv, text=True, capture_output=True,
                                  timeout=timeout, check=False,
                                  env={**os.environ, "DEBIAN_FRONTEND": "noninteractive", "LC_ALL": "C",
                                       **({"DOCKER_CONFIG": str(self.state / "docker")} if self.containers.enabled else {})})
            result = {"returncode": proc.returncode,
                      "stdout": proc.stdout, "stderr": proc.stderr,
                      "duration_seconds": round(time.monotonic() - started, 3)}
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            result = {"returncode": 124, "stdout": output,
                      "stderr": f"timeout after {timeout}s: {(exc.stderr or '')[-15000:]}",
                      "duration_seconds": round(time.monotonic() - started, 3)}
        except OSError as exc:
            result = {"returncode": 127, "stdout": "", "stderr": str(exc),
                      "duration_seconds": round(time.monotonic() - started, 3)}
        logged = dict(result)
        if sensitive:
            for key in ("stdout", "stderr"):
                logged[key + "_sha256"] = hashlib.sha256(str(result[key]).encode()).hexdigest()
                logged[key] = "[redacted: sensitive command output]"
        self.event("command_result", "Approved action completed", action=action, **logged)
        return result


    def software_inventory(self) -> dict[str, Any]:
        inventory: dict[str, Any] = {"apt_packages": {}, "extra": [], "errors": [], "package_version_conflicts": []}
        result = self.command("inventory_dpkg", ["dpkg-query", "-W",
                              "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n"])
        if result["returncode"]:
            inventory["errors"].append("dpkg inventory failed")
        else:
            for line in result["stdout"].splitlines():
                fields = line.split("\t")
                if len(fields) != 3:
                    inventory["errors"].append("Malformed dpkg inventory row")
                elif fields[2] == "installed":
                    inventory["apt_packages"][fields[0]] = fields[1]
        audit = self.command("inspect_dpkg_audit", ["dpkg", "--audit"])
        if audit["returncode"] or audit["stdout"].strip():
            inventory["errors"].append("Package database needs attention")

        def add(name: str, version: str, source: str, location: str) -> None:
            ignored = self.ignored.get(name.lower())
            inventory["extra"].append({"name": name, "version": version, "software_source": source,
                                       "location": location,
                                       "update_policy": "ignored" if ignored else "operator_review",
                                       **({"ignore_reason": ignored["reason"]} if ignored else {})})

        roots = [Path(p) for p in self.config.get("inventory", {}).get("roots", ["/opt", "/usr/local"])]
        splunk_home = Path(self.config.get("splunk", {}).get("home", "/opt/splunk"))
        locations = {splunk_home}
        for root in roots:
            if not root.is_absolute():
                inventory["errors"].append("Inventory root must be absolute: " + str(root))
                continue
            try:
                if root.exists():
                    locations.update(p for p in root.iterdir() if p.is_dir() and not p.is_symlink())
            except OSError as exc:
                inventory["errors"].append(f"Cannot list {root}: {type(exc).__name__}")
        for location in sorted(locations):
            if not location.exists():
                continue
            try:
                manifest = location / "etc/splunk.version"
                if manifest.is_file():
                    data = dict(line.split("=", 1) for line in manifest.read_text().splitlines() if "=" in line)
                    add(data.get("PRODUCT", "splunk"), data.get("VERSION", "unknown"), "splunk_manifest", str(location))
                    if location == splunk_home:
                        installed = inventory["apt_packages"].get("splunk")
                        actual = data.get("VERSION")
                        if installed and actual and not re.match(re.escape(actual) + r"(?:$|[+~-])", installed):
                            conflict = {"name": "splunk", "package_version": installed,
                                        "installed_version": actual, "location": str(location)}
                            if "splunk" not in self.ignored:
                                inventory["package_version_conflicts"].append(conflict)
                                self.event("anomaly", "Splunk manifest and package database versions disagree",
                                           severity="high", **conflict)
                    continue
                metadata = set()
                for pattern in ("lib/python*/site-packages/*.dist-info/METADATA",
                                "*/lib/python*/site-packages/*.dist-info/METADATA",
                                "python*/site-packages/*.dist-info/METADATA"):
                    metadata.update(location.glob(pattern))
                for path in sorted(metadata):
                    # Read metadata only; never import or execute discovered software.
                    with path.open() as handle:
                        header = handle.read(65536).partition("\n\n")[0]
                    name = re.search(r"^Name: (.+)$", header, re.MULTILINE)
                    version = re.search(r"^Version: (.+)$", header, re.MULTILINE)
                    if not name or not version:
                        raise ValueError("Invalid Python package metadata")
                    add(name[1], version[1], "python_metadata", str(path.parent))
                if location == Path("/opt/ai-sysadmin"):
                    with (location / "bin/ai-sysadmin").open() as handle:
                        controller_header = handle.read(4096)
                    installed_version = re.search(r'^VERSION = "([^"]+)"$', controller_header, re.MULTILINE)
                    add("ai-sysadmin", installed_version[1] if installed_version else "unknown", "controller", str(location))
                elif not metadata and any(location.iterdir()):
                    if location.name in ("bin", "sbin"):
                        for executable in sorted(location.iterdir()):
                            if executable.is_file():
                                add(executable.name, "unknown", "local_file", str(executable))
                    else:
                        add(location.name, "unknown", "directory", str(location))
            except (OSError, ValueError) as exc:
                inventory["errors"].append(f"Cannot inventory {location}: {type(exc).__name__}")
        for manager, argv in (("snap", ["snap", "list"]),
                              ("flatpak", ["flatpak", "list", "--system", "--app", "--columns=application,version"])):
            if not shutil.which(manager):
                continue
            result = self.command("inventory_" + manager, argv)
            if manager == "snap" and "No snaps are installed yet." in (result["stdout"] + result.get("stderr", "")):
                continue
            if result["returncode"]:
                inventory["errors"].append(manager + " inventory failed")
                continue
            for line in result["stdout"].splitlines():
                fields = line.split()
                if not fields or (manager == "snap" and fields[0] == "Name"):
                    continue
                add(fields[0], fields[1] if len(fields) > 1 else "unknown", manager, manager)
        self.event("inventory", "Software inventory collected", software=inventory)
        for item in inventory["extra"]:
            self.event("software", "Installed software detected", software_version=item["version"],
                       **{k: v for k, v in item.items() if k != "version"})
        unknown = [item["location"] for item in inventory["extra"]
                   if item["version"] == "unknown" and item["update_policy"] != "ignored"]
        if unknown:
            self.event("anomaly", "Software locations need version identification", severity="medium", locations=unknown)
        return inventory

    def inspect(self) -> dict[str, Any]:
        self.event("phase", "Inspection started", phase="inspection")
        disk = shutil.disk_usage("/")
        failed = self.command("inspect_failed_units",
                              ["systemctl", "list-units", "--state=failed,auto-restart",
                               "--no-legend", "--plain", "--all"])
        upgrades = self.command("inspect_upgradable_packages",
                                ["apt-get", "-s", "upgrade"], timeout=180)
        reboot_required = Path("/var/run/reboot-required").exists()
        failed_lines = [line for line in failed["stdout"].splitlines() if line.strip()]
        upgrade_lines = [line for line in upgrades["stdout"].splitlines()
                         if line.startswith("Inst ")]
        all_candidates, _ = upgrade_candidates(upgrades["stdout"])
        candidates, policy_errors = upgrade_candidates(upgrades["stdout"], set(self.ignored))
        inventory = self.software_inventory()
        container_inventory = self.containers.inspect()
        ignored_software = []
        for key, policy in sorted(self.ignored.items()):
            package_versions = [version for name, version in inventory["apt_packages"].items()
                                if software_name(name) == key]
            extras = [item for item in inventory["extra"] if item["name"].lower() == key]
            containers = [item for item in container_inventory.get("items", []) if item["name"].lower() == key]
            ignored_candidates = [item["after"] for item in all_candidates if software_name(item["name"]) == key]
            observed = ([item["version"] for item in extras] + package_versions +
                        [item["application_version"] for item in containers])
            row = {"software": policy["name"], "reason": policy["reason"],
                   "status": "update_available_ignored" if ignored_candidates else
                             ("ignored_current" if observed else "not_detected"),
                   "installed_versions": sorted(set(observed)),
                   "candidate_versions": sorted(set(ignored_candidates)),
                   "locations": sorted(set(item["location"] for item in extras)),
                   "sources": sorted(set(item["software_source"] for item in extras) |
                                     ({"apt"} if package_versions else set()) |
                                     ({"container"} if containers else set())),
                   "policy_file": str(self.ignore_file), "policy_sha256": self.ignore_policy_sha256}
            ignored_software.append(row)
            self.event("ignored", "Operator-approved software exception", **row)
        conflict_names = {item["name"] for item in inventory["package_version_conflicts"]}
        policy_errors.extend("Conflicting installed/package version requires review: " + item["name"]
                             for item in candidates if item["name"].split(":", 1)[0] in conflict_names)
        report = {
            "timestamp": stamp(), "hostname": socket.gethostname(),
            "root_free_percent": round(disk.free / disk.total * 100, 2),
            "root_free_bytes": disk.free, "failed_units": failed_lines,
            "upgradable_package_count": len(upgrade_lines),
            "upgradable_packages": upgrade_lines[:500],
            "package_candidates": candidates,
            "package_policy_errors": policy_errors,
            "ignored_software": ignored_software,
            "ignored_software_count": len(ignored_software),
            "software_inventory": inventory,
            "container_inventory": container_inventory,
            "container_count": len(container_inventory["items"]),
            "installed_package_count": len(inventory["apt_packages"]),
            "extra_software_count": len(inventory["extra"]),
            "reboot_required": reboot_required,
            "inspection_errors": [name for name, value in
                                  (("systemctl", failed), ("apt", upgrades))
                                  if value["returncode"] != 0] + self.ignore_errors + inventory["errors"] + container_inventory["errors"],
        }
        self.event("health", "Host inspection completed", **report)
        threshold = self.config["policy"]["minimum_free_root_percent"]
        if report["root_free_percent"] < threshold:
            self.event("anomaly", "Root filesystem free space is below policy",
                       severity="high", observed=report["root_free_percent"], threshold=threshold)
        if failed_lines:
            self.event("anomaly", "Failed or automatically restarting systemd units detected", severity="high",
                       failed_units=failed_lines)
        if reboot_required:
            self.event("anomaly", "Reboot is required but prohibited by policy",
                       severity="medium")
        if report["inspection_errors"]:
            self.event("anomaly", "Inspection command failed", severity="high",
                       errors=report["inspection_errors"])
        if policy_errors:
            self.event("anomaly", "Package changes require operator review", severity="high", errors=policy_errors)
        return report

    def blockers(self, inspection: dict[str, Any]) -> list[str]:
        reasons = []
        policy = self.config["policy"]
        if inspection["inspection_errors"]:
            reasons.append("Inspection incomplete")
        if inspection["root_free_percent"] < policy["minimum_free_root_percent"]:
            reasons.append("Insufficient root filesystem space")
        if len(inspection["failed_units"]) > policy.get("maximum_failed_units", 0):
            reasons.append("Failed systemd units exceed policy")
        if not policy.get("allow_service_restart", True):
            reasons.append("Package upgrades may restart services; policy prohibits this")
        return reasons

    def plan(self, inspection: dict[str, Any]) -> dict[str, Any]:
        # Reasoning is constrained to selecting from this action catalogue.
        actions: list[dict[str, str]] = []
        blocked = self.blockers(inspection)
        blocked.extend(inspection.get("package_policy_errors", []))
        container_updates, container_deferred = self.containers.plan(inspection.get("container_inventory", {}))
        reasoning = "Deterministic safety checks only"
        ai = self.config.get("ai", {})
        if ai.get("required", True):
            try:
                argv = ai.get("command", [])
                if not argv or not all(isinstance(x, str) for x in argv):
                    raise ValueError("AI planner command is not configured")
                # Full inventory stays in the audit/record; bound model context.
                planner_inspection = {k: v for k, v in inspection.items() if k != "software_inventory"}
                extra = sorted(inspection.get("software_inventory", {}).get("extra", []),
                               key=lambda item: (item.get("software_source") != "splunk_manifest",
                                                 item["name"] != "litellm", item["name"]))
                planner_inspection["package_version_conflicts"] = inspection.get("software_inventory", {}).get("package_version_conflicts", [])
                planner_inspection["extra_software"] = extra[:100]
                planner_inspection["extra_software_omitted"] = max(0, len(extra) - 100)
                planner_inspection["container_updates"] = container_updates
                planner_inspection["container_deferred"] = container_deferred
                request = {"inspection": planner_inspection, "allowed_actions": ["apt_update", "apt_upgrade", "container_update", "verify"],
                           "instruction": "Return JSON with proceed (boolean) and reasoning (string). Never return commands."}
                self.event("ai_request", "Requesting constrained planner assessment", request=request)
                response = subprocess.run(argv, input=json.dumps(request), text=True,
                                          capture_output=True, timeout=ai.get("timeout_seconds", 180), check=True,
                                          env={**os.environ, "AI_SYSADMIN_CONFIG": str(self.config_path)})
                assessment = json.loads(response.stdout)
                if not isinstance(assessment, dict) or type(assessment.get("proceed")) is not bool or not isinstance(assessment.get("reasoning"), str):
                    raise ValueError("Invalid planner response")
                reasoning = assessment["reasoning"]
                self.event("ai_response", "Planner assessment received", assessment=assessment)
                if not assessment["proceed"]:
                    blocked.append("AI planner deferred maintenance: " + reasoning)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                blocked.append("AI assessment unavailable: " + type(exc).__name__)
                self.event("anomaly", "AI planner unavailable or invalid", severity="high",
                           error_type=type(exc).__name__)
        min_free = self.config["policy"]["minimum_free_root_percent"]
        if not blocked:
            actions.append({"id": "apt_update", "reason": "Refresh package metadata"})
            actions.append({"id": "apt_upgrade", "reason": "Apply available safe upgrades"})
            if container_updates:
                actions.append({"id": "container_update", "reason": "Back up and apply prepared container image digests; verify readiness"})
        actions.append({"id": "verify", "reason": "Measure post-change host health"})
        plan = {"generated_at": stamp(), "actions": actions, "blocked_reasons": blocked,
                "reasoning": reasoning,
                "ignore_policy_sha256": self.ignore_policy_sha256,
                "container_updates": container_updates, "container_deferred": container_deferred,
                "policy": {"no_reboot": True, "no_dist_upgrade": True,
                           "no_major_upgrade": True, "no_remove": True,
                           "minimum_free_root_percent": min_free}}
        encoded = json.dumps(plan, sort_keys=True).encode()
        plan["sha256"] = hashlib.sha256(encoded).hexdigest()
        self.event("decision", "Constrained maintenance plan created", plan=plan)
        return plan

    def prepare(self, retry_of: str | None = None, reason: str | None = None) -> int:
        change_id = f"CHG-{utcnow():%Y%m%d}"
        if retry_of:
            if not re.fullmatch(CHANGE_ID_PATTERN, retry_of) or not reason or not reason.strip():
                print("Retry requires a valid --retry-of change ID and --reason.", file=sys.stderr)
                return 3
            previous = self.changes / f"{retry_of}.txt"
            if not previous.exists() or record_status(previous.read_text()) != "FAILED":
                print("Only a reviewed FAILED change can be retried; preserve and review interrupted runs first.",
                      file=sys.stderr)
                return 3
            # A retry of the same source always refers to the same successor.
            # Repeating the recovery command must not create another change.
            change_id = retry_of.split("-R")[0] + f"-R{int(retry_of.split('-R')[1]) + 1 if '-R' in retry_of else 1}"
        else:
            candidates = sorted(self.changes.glob(f"{change_id}-R*.txt"),
                                key=lambda p: int(p.stem.split("-R")[-1])
                                if re.fullmatch(CHANGE_ID_PATTERN, p.stem) else -1)
            candidates = [p for p in candidates if re.fullmatch(CHANGE_ID_PATTERN, p.stem)]
            if candidates:
                change_id = candidates[-1].stem
        pointer = self.state / "current-change"
        current = pointer.read_text().strip() if pointer.exists() else ""
        if current:
            if not re.fullmatch(CHANGE_ID_PATTERN, current):
                self.event("anomaly", "Invalid current-change reference", severity="high")
                print("Invalid current-change reference; operator review required.", file=sys.stderr)
                return 3
            current_record = self.changes / f"{current}.txt"
            if current_record.exists() and record_status(current_record.read_text()) == "RUNNING":
                print(f"{current} is RUNNING; operator review required before preparation.", file=sys.stderr)
                return 1
        else:
            # A lost pointer must not hide an interrupted run from an earlier day.
            for candidate in sorted(self.changes.glob("*.txt")):
                if not re.fullmatch(CHANGE_ID_PATTERN, candidate.stem):
                    continue
                try:
                    status = record_status(candidate.read_text())
                except (OSError, ValueError) as exc:
                    self.event("anomaly", "Cannot safely recover current-change reference",
                               severity="high", change_id=candidate.stem,
                               error_type=type(exc).__name__)
                    print(f"{candidate.stem}: unreadable or invalid record; operator review required.",
                          file=sys.stderr)
                    return 3
                if status == "RUNNING":
                    self.event("anomaly", "Pointer recovery refused: interrupted change",
                               severity="high", change_id=candidate.stem)
                    print(f"{candidate.stem} is RUNNING; operator review required before preparation.",
                          file=sys.stderr)
                    return 1
            self.event("recovery", "Missing or empty current-change reference; checking change history",
                       pointer_state="empty" if pointer.exists() else "missing")
        path = self.changes / f"{change_id}.txt"
        plan_path = self.state / f"{change_id}.plan.json"
        if path.exists():
            status = record_status(path.read_text())
            self.event("idempotency", "Existing change preserved", change_id=change_id, status=status)
            if status == "CLOSED":
                if not current:
                    atomic_write(pointer, change_id + "\n")
                    self.event("recovery", "Restored current-change reference to completed change",
                               change_id=change_id)
                print(f"{change_id} is CLOSED; no further action needed.")
                return 0
            if status != "PREPARED":
                print(f"{change_id} is {status}. After reviewing the failure, run prepare "
                      f"--retry-of {change_id} --reason 'reason for retry'.", file=sys.stderr)
                return 1
            try:
                plan = json.loads(plan_path.read_text())
                digest = plan.pop("sha256")
                if digest != hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest():
                    raise ValueError("Plan checksum mismatch")
                age = utcnow() - dt.datetime.fromisoformat(plan["generated_at"])
                if age.total_seconds() < 0 or age > dt.timedelta(hours=48):
                    raise ValueError("Prepared plan expired")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.event("anomaly", "Existing preparation is incomplete or invalid", severity="high",
                           change_id=change_id, error_type=type(exc).__name__)
                print(f"{change_id}: missing, invalid, or expired plan; operator review required.", file=sys.stderr)
                return 3
            if not pointer.exists() or pointer.read_text().strip() != change_id:
                atomic_write(pointer, change_id + "\n")
                self.event("recovery", "Restored current-change reference from validated preparation",
                           change_id=change_id)
            print(path)
            return 2 if plan["blocked_reasons"] else 0
        if plan_path.exists():
            print(f"{change_id}: orphaned plan requires operator review.", file=sys.stderr)
            return 3
        if retry_of:
            self.event("recovery", "Preparing a new change after operator review",
                       change_id=change_id, retry_of=retry_of, reason=reason)
        inspection = self.inspect()
        plan = self.plan(inspection)
        actions = "\n".join(f"- {a['id']}: {a['reason']}" for a in plan["actions"])
        blockers = "\n".join(f"- {item}" for item in plan["blocked_reasons"]) or "- None"
        text = f"""ITIL CHANGE RECORD
Change ID: {change_id}
Host: {inspection['hostname']}
Prepared at: {stamp()}
Retry of: {retry_of or "None"}
Retry reason: {json.dumps(reason) if reason else "None"}
Status: PREPARED
Risk: Low (allowlisted package maintenance; reboot prohibited)

Reason
Weekly health inspection and supported Ubuntu package maintenance.

Inspection
{json.dumps(inspection, indent=2, sort_keys=True)}

Implementation plan
{actions}

Blocked reasons
{blockers}

Safety boundaries
- No reboot, release upgrade, major software upgrade, package removal, or downgrade
- No autonomous access, firewall, network, user, sudo, storage, or boot configuration changes
- Standalone extra software is inventoried; updates require a reviewed procedure
- Only configured Compose services may update; held services and major version changes are excluded
- Container updates use prepared digests, stopped-data backups, and readiness verification
- Package versions are simulated after metadata refresh, safety-checked and pinned before execution

Validation plan
- Re-run host inspection
- Check failed systemd units and root filesystem capacity
- Verify actual installed versions and dpkg consistency
- Inventory APT and extra software before and after maintenance
- Record package results and reboot-required state

Backout plan
- Stop execution on any failed allowlisted action
- Do not attempt automatic package downgrade or reboot
- Escalate any incomplete dpkg state for operator review

Closure
Pending maintenance execution.
"""
        atomic_write(path, text)
        atomic_write(self.state / f"{change_id}.plan.json", json.dumps(plan, indent=2) + "\n")
        atomic_write(self.state / "current-change", change_id + "\n")
        self.event("change", "Change record prepared", change_id=change_id, path=str(path),
                   blocked=bool(plan["blocked_reasons"]))
        print(path)
        return 2 if plan["blocked_reasons"] else 0


    def approved_upgrade(self, inspection: dict[str, Any]) -> tuple[list[str], list[dict[str, str]], list[str]]:
        simulated = self.command("simulate_refreshed_upgrade", ["apt-get", "-s", "--no-remove", "upgrade"], 180)
        if simulated["returncode"]:
            return [], [], ["Refreshed package simulation failed"]
        packages, errors = upgrade_candidates(simulated["stdout"], set(self.ignored))
        conflicts = {item["name"] for item in inspection.get("software_inventory", {}).get("package_version_conflicts", [])}
        errors.extend("Conflicting installed/package version requires review: " + item["name"]
                      for item in packages if item["name"].split(":", 1)[0] in conflicts)
        for package in packages:
            result = self.command("verify_upgrade_direction", ["dpkg", "--compare-versions",
                                  package["before"], "lt", package["after"]])
            if result["returncode"]:
                errors.append("Downgrade or invalid version refused: " + package["name"])
        if errors or not packages:
            return [], packages, errors
        args = ["--no-remove", "--only-upgrade", "install"] + [p["name"] + "=" + p["after"] for p in packages]
        # Validate dependencies too, then execute these exact versions.
        pinned = self.command("simulate_exact_upgrade", ["apt-get", "-s"] + args, 180)
        checked, problems = upgrade_candidates(pinned["stdout"])
        ignored_changes = [item for item in checked if software_name(item["name"]) in self.ignored]
        if ignored_changes:
            errors.append("Exact package transaction would change ignored software: " +
                          ", ".join(item["name"] for item in ignored_changes))
        if pinned["returncode"] or problems or sorted(checked, key=lambda p: p["name"]) != sorted(packages, key=lambda p: p["name"]):
            errors.append("Exact package transaction changed or violates policy")
        self.event("decision", "Evaluated exact package transaction after metadata refresh",
                   packages=packages, errors=errors, argv=["apt-get", "-y"] + args)
        return ["apt-get", "-y"] + args, packages, errors

    def verify_software(self, pre: dict[str, Any], post: dict[str, Any],
                        expected: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[str]]:
        before = pre.get("software_inventory", {}).get("apt_packages", {})
        after = post.get("software_inventory", {}).get("apt_packages", {})
        changes = [{"name": name, "before": before.get(name), "after": after.get(name)}
                   for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
        errors = ["Installed package disappeared: " + name for name in before.keys() - after.keys()]
        if not self.dry_run:
            for item in expected:
                # apt may omit :arch for native packages; dpkg includes it for Multi-Arch.
                observed = after.get(item["name"])
                if observed is None and ":" not in item["name"]:
                    matches = [v for k, v in after.items() if k.split(":", 1)[0] == item["name"]]
                    observed = matches[0] if len(matches) == 1 else None
                if observed != item["after"]:
                    errors.append(f"Expected version not installed: {item['name']} expected {item['after']}, observed {observed}")
        extra_before = {i["location"] + ":" + i["name"]: i["version"]
                        for i in pre.get("software_inventory", {}).get("extra", [])}
        extra_after = {i["location"] + ":" + i["name"]: i["version"]
                       for i in post.get("software_inventory", {}).get("extra", [])}
        extra_changes = [{"location_name": k, "before": extra_before.get(k), "after": extra_after.get(k)}
                         for k in sorted(extra_before.keys() | extra_after.keys()) if extra_before.get(k) != extra_after.get(k)]
        if extra_changes:
            errors.append("Software outside APT changed during maintenance; review required")
        self.event("verification", "Compared actual software state before and after maintenance",
                   package_changes=changes, extra_changes=extra_changes, expected=expected,
                   errors=errors, simulated=self.dry_run)
        if errors:
            self.event("anomaly", "Software verification failed", severity="high", errors=errors)
        return changes, errors

    def maintain(self) -> int:
        try:
            return self._maintain()
        except Exception as exc:
            self.event("anomaly", "Maintenance aborted by exception", severity="high",
                       error_type=type(exc).__name__)
            pointer = self.state / "current-change"
            change_id = pointer.read_text().strip() if pointer.exists() else ""
            record = self.changes / f"{change_id}.txt"
            if re.fullmatch(CHANGE_ID_PATTERN, change_id) and record.exists():
                self.close(record, record.read_text(), change_id, "FAILED",
                           "Execution aborted: " + type(exc).__name__ + "; operator review required")
            else:
                self.event("closure", "Maintenance aborted without valid change record", status="FAILED")
            return 1

    def _maintain(self) -> int:
        pointer = self.state / "current-change"
        if not pointer.exists():
            self.event("anomaly", "Maintenance refused: no prepared change", severity="high")
            print("No prepared change. Run prepare first.", file=sys.stderr)
            self.event("closure", "No prepared change; no actions executed", status="FAILED")
            return 3
        change_id = pointer.read_text(encoding="utf-8").strip()
        if not re.fullmatch(CHANGE_ID_PATTERN, change_id):
            self.event("closure", "Invalid change reference", status="FAILED")
            return 3
        record = self.changes / f"{change_id}.txt"
        plan_path = self.state / f"{change_id}.plan.json"
        if not record.exists() or not plan_path.exists():
            self.event("anomaly", "Maintenance refused: change artifacts missing",
                       severity="high", change_id=change_id)
            self.event("closure", "Missing change artifacts; no actions executed", status="FAILED")
            return 3
        record_text = record.read_text(encoding="utf-8")
        try:
            status = record_status(record_text)
        except ValueError as exc:
            self.event("anomaly", str(exc), severity="high", change_id=change_id)
            self.event("closure", "Invalid change header; no actions executed",
                       change_id=change_id, status="FAILED")
            return 1
        if status == "CLOSED":
            self.event("idempotency", "Closed change requires no further action", change_id=change_id)
            return 0
        if status in ("FAILED", "RUNNING"):
            print(f"{change_id} is {status}; operator review required. See {record}.", file=sys.stderr)
            self.event("closure", "Terminal or interrupted change requires operator review",
                       change_id=change_id, status="FAILED")
            return 1
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        digest = plan.pop("sha256", None)
        if digest != hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest():
            self.close(record, record_text, change_id, "FAILED", "Plan checksum mismatch")
            return 1
        age = utcnow() - dt.datetime.fromisoformat(plan["generated_at"])
        if age.total_seconds() < 0 or age > dt.timedelta(hours=48):
            self.close(record, record_text, change_id, "FAILED", "Prepared plan expired")
            return 1
        if plan["blocked_reasons"]:
            self.close(record, record_text, change_id, "FAILED",
                       "Maintenance blocked during preparation: " + "; ".join(plan["blocked_reasons"]))
            return 2
        pre = self.inspect()
        reasons = self.blockers(pre)
        if plan.get("ignore_policy_sha256") != self.ignore_policy_sha256:
            reasons.append("IGNORE.md changed after preparation")
        reasons.extend(self.containers.validate(plan.get("container_updates", [])))
        if reasons:
            self.close(record, record_text, change_id, "FAILED", "; ".join(reasons))
            return 2
        expected_actions = ["apt_update", "apt_upgrade"]
        if plan.get("container_updates"):
            expected_actions.append("container_update")
        expected_actions.append("verify")
        if [a["id"] for a in plan["actions"]] != expected_actions:
            self.close(record, record_text, change_id, "FAILED", "Invalid action sequence")
            return 1
        record_text = replace_record_status(record_text, "RUNNING")
        atomic_write(record, record_text)
        timeout = self.config["policy"]["package_update_timeout_seconds"]
        results = []
        expected_packages = []
        catalogue = {
            "apt_update": (["apt-get", "-o", "APT::Update::Error-Mode=any", "update"], timeout),
            "apt_upgrade": ([], timeout),
        }
        for action in plan["actions"]:
            if action["id"] == "verify":
                continue
            if action["id"] == "container_update":
                container_results = self.containers.apply(plan["container_updates"], change_id)
                failed = any(item["returncode"] for item in container_results)
                results.append({"action": "container_update", "returncode": int(failed), "containers": container_results})
                if failed:
                    break
                continue
            if action["id"] not in catalogue:
                self.event("anomaly", "Unknown action rejected", severity="high", action=action)
                results.append({"action": action["id"], "returncode": 126})
                break
            argv, action_timeout = catalogue[action["id"]]
            if action["id"] == "apt_upgrade":
                argv, expected_packages, errors = self.approved_upgrade(pre)
                if errors:
                    self.event("anomaly", "Package transaction refused by safety policy", severity="high",
                               change_id=change_id, errors=errors)
                    results.append({"action": "apt_upgrade", "returncode": 2, "errors": errors})
                    break
                if not argv:
                    self.event("idempotency", "No package versions need updating", change_id=change_id)
                    results.append({"action": "apt_upgrade", "returncode": 0, "skipped": True})
                    continue
            result = self.command(action["id"], argv, action_timeout, mutate=True)
            results.append({"action": action["id"], "returncode": result["returncode"]})
            if result["returncode"] != 0:
                self.event("anomaly", "Package maintenance action failed", severity="high",
                           change_id=change_id, action=action["id"],
                           returncode=result["returncode"], stderr=result.get("stderr", ""))
                break
        post = self.inspect()
        failures = [item for item in results if item["returncode"] != 0]
        package_changes, verification_errors = self.verify_software(pre, post, expected_packages)
        succeeded = not failures and not self.blockers(post) and not verification_errors
        status = "CLOSED" if succeeded else "FAILED"
        summary = ("Approved maintenance actions completed successfully."
                   if succeeded else f"Maintenance needs attention. Failures: {failures}")
        if self.blockers(post):
            summary += " Health findings: " + "; ".join(self.blockers(post))
        if post["reboot_required"]:
            summary += " Reboot is required and was not performed."
        if verification_errors:
            summary += " Verification findings: " + "; ".join(verification_errors)
        if post.get("software_inventory", {}).get("package_version_conflicts"):
            summary += " Installed software and package database version conflicts still require review."
        extra_count = post.get("extra_software_count", 0)
        if extra_count:
            summary += f" {extra_count} extra software entries inventoried; updates outside APT require operator review."
        summary += f" Actual APT package version changes: {len(package_changes)}."
        if plan.get("container_deferred"):
            summary += " Container updates deferred for review: " + json.dumps(plan["container_deferred"])
        if plan.get("container_updates"):
            summary += " Container image results and backup locations are recorded below."
        details = (summary + "\nPackage changes: " + json.dumps(package_changes)
                   + "\nResults: " + json.dumps(results) + "\nPost-health: " + json.dumps(post))
        self.close(record, record_text, change_id, status, details)
        return 0 if succeeded else 1

    def close(self, record: Path, original: str, change_id: str,
              status: str, details: str) -> None:
        updated = replace_record_status(original, status)
        updated = updated.replace("Closure\nPending maintenance execution.",
                                  f"Closure\nClosed at: {stamp()}\n{details}")
        atomic_write(record, updated)
        self.event("closure", "Change record closed", change_id=change_id,
                   status=status, closing_remark=details)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "maintain", "inspect", "containers"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-of", help="Prepare a separate successor to a reviewed FAILED change")
    parser.add_argument("--reason", help="Audit reason for retrying a failed change")
    args = parser.parse_args()
    if (args.retry_of or args.reason) and (args.command != "prepare" or not args.retry_of or not args.reason):
        parser.error("--retry-of and --reason must be used together with prepare")
    if os.geteuid() != 0 and not args.dry_run:
        parser.error("run as root, or use --dry-run")
    controller = Controller(args.config, args.dry_run)
    lock_path = controller.state / "controller.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            controller.event("anomaly", "Another lifecycle process holds the lock", severity="medium")
            return 75
        if args.command == "prepare":
            return controller.prepare(args.retry_of, args.reason)
        if args.command == "maintain":
            return controller.maintain()
        if args.command == "containers":
            inventory = controller.containers.inspect()
            updates, deferred = controller.containers.plan(inventory)
            result = {"inventory": inventory, "updates": updates, "deferred": deferred}
            controller.event("decision", "Container update preview completed", **result)
            print(json.dumps(result, indent=2))
            return 2 if inventory["errors"] or deferred else 0
        controller.inspect()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
