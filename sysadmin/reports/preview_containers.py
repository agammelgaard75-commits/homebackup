"""Read-only live preview using staged container policy; no images pulled."""
import json
from pathlib import Path
import sys
sys.path.insert(0, "/home/bot/sysadmin/src")
from ai_sysadmin import Controller
from container_maintenance import ContainerMaintenance

POLICY = {"enabled": True, "services": [{
    "name": "n8n", "project": "n8n", "service": "n8n",
    "compose_files": ["/home/bot/n8n/docker-compose.yml"],
    "image": "docker.n8n.io/n8nio/n8n:latest", "hold": False,
    "health_url": "http://127.0.0.1:5678/healthz/readiness",
    "health_timeout_seconds": 180, "maximum_backup_bytes": 1073741824,
}]}

if __name__ == "__main__":
    c = Controller(Path("/etc/ai-sysadmin/config.toml"), dry_run=True)
    c.config["containers"] = POLICY
    c.containers = ContainerMaintenance(c)
    inventory = c.containers.inspect()
    updates, deferred = c.containers.plan(inventory)
    assert not inventory["errors"], inventory["errors"]
    assert inventory["items"][0]["name"] == "n8n"
    result = {"inventory": inventory, "updates": updates, "deferred": deferred}
    c.event("decision", "Staged container update preview", **result)
    print(json.dumps(result, indent=2))
