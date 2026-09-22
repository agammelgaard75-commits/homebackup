"""Allowlisted Compose image maintenance; no package installation inside containers."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
VERSION_LABEL = "org.opencontainers.image.version"
DEPENDENCY_LABEL = "com.docker.dhi.version"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def release(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+][A-Za-z0-9._+-]+)?", str(value))
    if not match:
        raise ValueError("Unrecognized image software version")
    return tuple(int(part) for part in match.groups())


def version_errors(old, new):
    errors = []
    for key, value in old.items():
        try:
            a, b = release(value), release(new.get(key, ""))
            if a[0] != b[0] or b < a:
                errors.append(f"{key}: major change or downgrade {value} -> {new.get(key)}")
        except ValueError:
            errors.append(f"{key}: missing or unrecognized version")
    if VERSION_LABEL not in old:
        errors.append("Image has no supported application version label")
    return errors


class ContainerMaintenance:
    def __init__(self, controller):
        self.c = controller
        self.config = controller.config.get("containers", {})
        self.enabled = self.config.get("enabled", False)
        self.directory = controller.state / "containers"
        if self.enabled:
            (controller.state / "docker").mkdir(mode=0o700, exist_ok=True)

    def services(self):
        services = self.config.get("services", [])
        names = [s["name"] for s in services]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate managed container name")
        return services

    def command(self, action, argv, timeout=120, mutate=False, sensitive=False):
        result = self.c.command(action, argv, timeout=timeout, mutate=mutate, sensitive=sensitive)
        if result["returncode"]:
            raise RuntimeError(f"{action} failed (exit {result['returncode']}); see audit")
        return result["stdout"]

    def json_command(self, action, argv):
        return json.loads(self.command(action, argv, sensitive=True))

    def current(self, name):
        data = self.json_command("container_inspect", ["docker", "inspect", name])[0]
        labels = data["Config"].get("Labels") or {}
        image = self.json_command("container_image_inspect", ["docker", "image", "inspect", data["Image"]])[0]
        image_labels = image["Config"].get("Labels") or {}
        versions = {key: image_labels[key] for key in (VERSION_LABEL, DEPENDENCY_LABEL) if key in image_labels}
        return {
            "name": data["Name"].lstrip("/"), "id": data["Id"], "image_id": data["Image"],
            "image_ref": data["Config"]["Image"], "digests": image.get("RepoDigests") or [],
            "platform": image["Os"] + "/" + image["Architecture"],
            "versions": versions, "application_version": versions.get(VERSION_LABEL, "unknown"),
            "dependency_version": versions.get(DEPENDENCY_LABEL, "unknown"), "running": data["State"]["Running"],
            "health": data["State"].get("Health", {}).get("Status", "not_configured"),
            "restart_count": data["RestartCount"], "project": labels.get("com.docker.compose.project"),
            "service": labels.get("com.docker.compose.service"),
            "compose_hash": labels.get("com.docker.compose.config-hash"),
            "mounts": sorted([{k: m.get(k) for k in ("Type", "Name", "Source", "Destination", "RW")} for m in data["Mounts"]], key=lambda m: m["Destination"]),
            "runtime_hash": fingerprint({k: data[k] for k in ("Config", "HostConfig", "Mounts")}),
        }

    def inspect(self):
        report = {"items": [], "errors": []}
        if not self.enabled:
            return report
        try:
            policies = {s["name"]: s for s in self.services()}
            names = self.command("container_list", ["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines()
            for name in names:
                item = self.current(name)
                policy = policies.get(name)
                item["update_policy"] = "hold" if policy and policy.get("hold") else "automatic" if policy else "report_only"
                report["items"].append(item)
                self.c.event("container", "Container image inventory", **item)
                if policy and (not item["running"] or item["health"] in ("unhealthy", "starting")):
                    report["errors"].append(f"{name}: managed container is not healthy/running")
                if not policy:
                    self.c.event("anomaly", "Container has no reviewed update policy", severity="medium", container=name)
            report["errors"].extend(name + ": configured container missing" for name in policies if name not in names)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            report["errors"].append(str(exc))
        if report["errors"]:
            self.c.event("anomaly", "Container inventory needs attention", severity="high", errors=report["errors"])
        self.c.event("container_inventory", "Container inventory completed", names=[i["name"] for i in report["items"]], errors=report["errors"])
        return report

    def policy(self, name):
        return next(s for s in self.services() if s["name"] == name)

    def override(self, service):
        return self.directory / service["name"] / "image.json"

    def compose(self, service, override=None):
        for key in ("name", "project", "service"):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", service[key]):
                raise ValueError("Invalid container policy identifier")
        paths = service["compose_files"]
        if not paths or any(not Path(p).is_absolute() or not Path(p).is_file() for p in paths):
            raise ValueError("Compose files must be existing absolute local paths")
        argv = ["docker", "compose", "--project-name", service["project"],
                "--project-directory", str(Path(paths[0]).parent)]
        for path in paths:
            argv += ["--file", path]
        effective = override if override is not None else self.override(service)
        if effective.exists():
            argv += ["--file", str(effective)]
        return argv

    def compose_state(self, service):
        argv = self.compose(service)
        model = self.json_command("container_compose_config", argv + ["config", "--format", "json"])
        if service["service"] not in model["services"]:
            raise ValueError("Configured Compose service is missing")
        spec = model["services"][service["service"]]
        if "build" in spec or spec.get("deploy", {}).get("replicas", 1) != 1:
            raise ValueError("Builds and replicated services need a separate update procedure")
        hashes = self.command("container_compose_hash", argv + ["config", "--hash", service["service"]]).split()
        if len(hashes) != 2 or hashes[0] != service["service"]:
            raise ValueError("Cannot identify Compose service fingerprint")
        return model, hashes[1]

    def candidate(self, service, current):
        reference = service["image"]
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9./_:@-]+", reference):
            raise ValueError("Invalid registry image reference")
        manifest = self.json_command("container_registry_manifest", [
            "docker", "buildx", "imagetools", "inspect", reference, "--format", "{{json .Manifest}}"])
        repository = reference.split("@", 1)[0]
        if ":" in repository.rsplit("/", 1)[-1]:
            repository = repository.rsplit(":", 1)[0]
        digest = manifest.get("digest", "")
        if "manifests" in manifest:
            matches = [m for m in manifest["manifests"] if
                       m.get("platform", {}).get("os", "") + "/" + m.get("platform", {}).get("architecture", "") == current["platform"]]
            if len(matches) != 1:
                raise ValueError("Cannot select a unique container platform")
            digest = matches[0]["digest"]
        if not DIGEST.fullmatch(digest):
            raise ValueError("Invalid registry image digest")
        pinned = repository + "@" + digest
        raw = self.json_command("container_registry_config_digest", [
            "docker", "buildx", "imagetools", "inspect", pinned, "--raw"])
        image_id = raw["config"]["digest"]
        if not DIGEST.fullmatch(image_id):
            raise ValueError("Invalid registry image config digest")
        config = self.json_command("container_registry_versions", [
            "docker", "buildx", "imagetools", "inspect", pinned, "--format", "{{json .Image}}"])
        if "config" not in config:
            config = config[current["platform"]]
        labels = config["config"].get("Labels") or {}
        versions = {key: labels[key] for key in (VERSION_LABEL, DEPENDENCY_LABEL) if key in labels}
        return {"image": pinned, "image_id": image_id, "versions": versions}

    def plan(self, inspection):
        updates, deferred = [], []
        if not self.enabled:
            return updates, deferred
        items = inspection.get("items", [])
        by_name = {item["name"]: item for item in items}
        for service in self.services():
            name = service["name"]
            if name.lower() in self.c.ignored:
                self.c.event("idempotency", "Container omitted by IGNORE.md", container=name,
                             reason=self.c.ignored[name.lower()]["reason"])
                continue
            if service.get("hold", False):
                self.c.event("idempotency", "Container held at current image", container=name)
                continue
            target = None
            try:
                current = by_name[name]
                if not current["running"] or current["health"] in ("unhealthy", "starting"):
                    raise ValueError("Container is not healthy/running")
                if (current["project"], current["service"]) != (service["project"], service["service"]):
                    raise ValueError("Container does not belong to the configured Compose service")
                model, config_hash = self.compose_state(service)
                if config_hash != current["compose_hash"]:
                    raise ValueError("Compose configuration differs from running container; review drift first")
                if not service.get("health_url") and current["health"] == "not_configured":
                    raise ValueError("Automatic update requires a readiness URL or Docker healthcheck")
                writable = [m for m in current["mounts"] if m["RW"]]
                if not writable and not service.get("stateless", False):
                    raise ValueError("Declare stateless=true or provide persistent data mounts")
                if any(m["Type"] not in ("bind", "volume") for m in writable):
                    raise ValueError("Unsupported writable mount type")
                for other in items:
                    if other["name"] != name and other["running"] and any(
                        m["Source"] == n["Source"] and n["RW"] for m in writable for n in other["mounts"]):
                        raise ValueError("Writable data is shared with another running container")
                target = self.candidate(service, current)
                if target["image_id"] == current["image_id"]:
                    self.c.event("idempotency", "Container image is already current", container=name, image_id=current["image_id"])
                    continue
                errors = version_errors(current["versions"], target["versions"])
                if errors:
                    raise ValueError("; ".join(errors))
                repository = target["image"].split("@", 1)[0]
                old_images = [d for d in current["digests"] if d.startswith(repository + "@sha256:")]
                if not old_images:
                    raise ValueError("Current image lacks a recoverable registry digest")
                update = {"name": name, "policy_hash": fingerprint(service),
                          "compose_hash": config_hash, "runtime_hash": current["runtime_hash"],
                          "container_id": current["id"], "before_image_id": current["image_id"],
                          "before_image": old_images[0], "before_versions": current["versions"],
                          "mounts": current["mounts"], **target}
                updates.append(update)
                self.c.event("decision", "Container image update prepared", update=update)
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                finding = {"name": name, "reason": str(exc), "candidate": target}
                deferred.append(finding)
                self.c.event("anomaly", "Container image update deferred", severity="medium", container=name,
                             reason=str(exc), candidate=target)
        return updates, deferred

    def validate(self, updates):
        errors = []
        for update in updates:
            try:
                service = self.policy(update["name"])
                if not self.enabled or service.get("hold") or fingerprint(service) != update["policy_hash"]:
                    raise ValueError("Container policy changed or is held")
                current = self.current(update["name"])
                _, config_hash = self.compose_state(service)
                if current["image_id"] == update["image_id"]:
                    continue
                if current["id"] != update["container_id"] or current["runtime_hash"] != update["runtime_hash"] or config_hash != update["compose_hash"]:
                    raise ValueError("Container or Compose state changed after preparation")
                if not current["running"] or current["health"] in ("unhealthy", "starting"):
                    raise ValueError("Container is no longer healthy/running")
                if version_errors(current["versions"], update["versions"]):
                    raise ValueError("Prepared versions violate update policy")
            except (OSError, ValueError, KeyError, RuntimeError, StopIteration) as exc:
                errors.append(update["name"] + ": " + str(exc))
        return errors

    def readiness(self, service, image_id, timeout=120):
        deadline = time.monotonic() + timeout
        stable_since = None
        restarts = None
        while True:
            current = self.current(service["name"])
            ready = current["running"] and current["image_id"] == image_id and current["health"] not in ("unhealthy", "starting")
            if restarts is not None and current["restart_count"] != restarts:
                ready = False
            restarts = current["restart_count"]
            url = service.get("health_url")
            if url:
                if not re.fullmatch(r"https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]+)?/[^\s]*", url):
                    raise ValueError("Readiness URL must be a loopback HTTP(S) endpoint")
                result = self.c.command("container_readiness", ["curl", "--fail", "--silent",
                    "--max-time", "5", "--output", "/dev/null", "--write-out", "%{http_code}", url], timeout=10)
                ready = ready and result["returncode"] == 0 and result.get("stdout", "").strip() == "200"
            if ready:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= service.get("stability_seconds", 10):
                    return current
            else:
                stable_since = None
            if time.monotonic() >= deadline:
                raise RuntimeError("Container readiness/stability verification timed out")
            time.sleep(2)

    def archive(self, container, mount, target, maximum_bytes):
        argv = ["prlimit", f"--fsize={maximum_bytes}", "--", "docker", "cp",
                container + ":" + mount["Destination"].rstrip("/") + "/.", "-"]
        self.c.event("command_start", "Back up stopped container data", action="container_backup",
                     argv=argv, destination=str(target), maximum_bytes=maximum_bytes)
        with target.open("xb") as output:
            os.chmod(target, 0o600)
            result = subprocess.run(argv, stdout=output, stderr=subprocess.PIPE, timeout=600, check=False,
                                    env={**os.environ, "DOCKER_CONFIG": str(self.c.state / "docker")})
            output.flush()
            os.fsync(output.fileno())
        self.c.event("command_result", "Container data backup command completed",
                     action="container_backup", returncode=result.returncode, bytes=target.stat().st_size,
                     stderr_sha256=hashlib.sha256(result.stderr).hexdigest())
        if result.returncode:
            raise RuntimeError("Container data backup failed")
        files = 0
        with tarfile.open(target) as archive:
            for member in archive:
                if member.isfile():
                    handle = archive.extractfile(member)
                    while handle.read(1024 * 1024):
                        pass
                    files += 1
        with target.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        self.c.event("verification", "Stopped-data archive read back and checksummed",
                     archive=str(target), sha256=digest, files=files)
        return {"path": str(target), "sha256": digest, "files": files}

    def apply(self, updates, change_id):
        results = []
        for update in updates:
            name = update["name"]
            service = self.policy(name)
            errors = self.validate([update])
            if errors:
                return results + [{"name": name, "returncode": 2, "errors": errors}]
            if self.c.dry_run:
                results.append({"name": name, "returncode": 0, "simulated": True, "image": update["image"]})
                continue
            current = self.current(name)
            if current["image_id"] == update["image_id"]:
                self.readiness(service, update["image_id"])
                results.append({"name": name, "returncode": 0, "skipped": True})
                continue
            backup = self.directory / name / "backups" / change_id
            stopped = replacement_started = False
            try:
                atomic_write = self.c.write
                backup.mkdir(parents=True, mode=0o700, exist_ok=False)
                os.chmod(backup, 0o700)
                model, _ = self.compose_state(service)
                atomic_write(backup / "compose-before.json", json.dumps(model), 0o600)
                atomic_write(backup / "update.json", json.dumps(update, indent=2), 0o600)
                self.command("container_pull", ["docker", "pull", update["image"]], timeout=900, mutate=True)
                pulled = self.json_command("container_verify_pulled_image", ["docker", "image", "inspect", update["image"]])[0]
                if pulled["Id"] != update["image_id"]:
                    raise RuntimeError("Pulled image does not match prepared config digest")
                labels = pulled["Config"].get("Labels") or {}
                if any(labels.get(k) != v for k, v in update["versions"].items()):
                    raise RuntimeError("Pulled image versions differ from preparation")
                errors = self.validate([update])
                if errors:
                    raise RuntimeError("; ".join(errors))
                self.readiness(service, update["before_image_id"])
                writable = [m for m in update["mounts"] if m["RW"]]
                maximum = int(service.get("maximum_backup_bytes", 1024 * 1024 * 1024))
                free = shutil.disk_usage(backup).free
                reserve = max(1024 * 1024 * 1024, int(shutil.disk_usage(backup).total * self.c.config["policy"]["minimum_free_root_percent"] / 100))
                if maximum <= 0 or free - maximum * len(writable) < reserve:
                    raise RuntimeError("Insufficient disk headroom for bounded container backups")
                stopped = True
                self.command("container_stop_for_backup", ["docker", "stop", "--time", "60", current["id"]], mutate=True)
                if self.current(name)["running"]:
                    raise RuntimeError("Container did not stop for consistent backup")
                archives = [self.archive(current["id"], mount, backup / f"mount-{i}.tar", maximum)
                            for i, mount in enumerate(writable)]
                atomic_write(backup / "archives.json", json.dumps(archives, indent=2), 0o600)
                candidate_file = backup / "candidate-image.json"
                content = json.dumps({"services": {service["service"]: {"image": update["image"]}}}) + "\n"
                atomic_write(candidate_file, content, 0o600)
                old_content = json.dumps({"services": {service["service"]: {"image": update["before_image"]}}}) + "\n"
                atomic_write(backup / "previous-image.json", old_content, 0o600)
                replacement_started = True
                self.command("container_recreate", self.compose(service, candidate_file) + [
                    "up", "--detach", "--no-deps", "--no-build", "--pull", "never", service["service"]],
                    timeout=180, mutate=True, sensitive=True)
                verified = self.readiness(service, update["image_id"], int(service.get("health_timeout_seconds", 180)))
                if verified["mounts"] != update["mounts"]:
                    raise RuntimeError("Container mounts changed after update")
                atomic_write(self.override(service), content, 0o600)
                result = {"name": name, "returncode": 0, "before_image": update["before_image"],
                          "image": update["image"], "versions": update["versions"], "backup": str(backup)}
                atomic_write(backup / "result.json", json.dumps(result), 0o600)
                self.c.event("verification", "Container image and readiness verified; mounts preserved", **result)
                results.append(result)
            except Exception as exc:
                if stopped and not replacement_started:
                    self.c.command("container_resume_after_backup_failure", ["docker", "start", current["id"]], mutate=True)
                    try:
                        self.readiness(service, update["before_image_id"])
                    except Exception:
                        self.c.event("anomaly", "Original container recovery needs attention", severity="high", container=name)
                result = {"name": name, "returncode": 1, "error": str(exc), "backup": str(backup),
                          "replacement_started": replacement_started}
                self.c.event("anomaly", "Container update failed; preserve backups and review recovery",
                             severity="high", **result)
                results.append(result)
                break
        return results
