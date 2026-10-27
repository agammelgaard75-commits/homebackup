"""Run ONLY in the isolated release rehearsal, against synthetic data."""
import os
import secrets
import socket
import sys
from datetime import timedelta

import django
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from apps.accounts.credentials import issue_credential
from apps.customers.models import Customer

if os.environ.get("ALLOW_DISPOSABLE_SMOKE") != "portal-release-verify" or settings.AUTH_MODE != "local":
    raise SystemExit("Run only against the explicit disposable, local-auth release rehearsal.")

# Route the public hostname to the private proxy in this isolated Docker network.
# TLS still verifies the public hostname and the exported Caddy public CA.
domain = os.environ["PORTAL_DOMAIN"]
original_lookup = socket.getaddrinfo
def lookup(host, *args, **kwargs):
    return original_lookup("proxy" if host == domain else host, *args, **kwargs)
socket.getaddrinfo = lookup
base = f"https://{domain}"
password = secrets.token_urlsafe(32)
users = {}
clients = {}
for role in ("Viewer", "Editor", "Administrator"):
    user = get_user_model().objects.create_user(username=f"release-{role}-{secrets.token_hex(4)}", password=password)
    user.groups.add(Group.objects.get(name=role))
    users[role] = user
admin = users["Administrator"]
for role, user in users.items():
    credential, token = issue_credential(actor=admin, user=user, name="Disposable release verification",
        scopes=["read", "write", "import", "audit", "cleanup"], expires_at=timezone.now() + timedelta(hours=1))
    client = requests.Session()
    client.trust_env = False
    client.verify = "/tmp/release-ca.crt"
    client.headers["Authorization"] = f"Bearer {token}"
    clients[role] = client
count = 0
def api(role, method, path, expected=200, **kwargs):
    global count
    response = clients[role].request(method, base + "/api/v1/" + path, timeout=20, **kwargs)
    assert response.status_code == expected, (method, path, response.status_code)
    count += 1
    return response.json()

customer = api("Editor", "POST", "customers/", 201, json={"name": "Disposable release customer"})
second = api("Editor", "POST", "customers/", 201, json={"name": "Disposable second customer"})
cid = customer["id"]
api("Viewer", "PATCH", f"customers/{cid}/", 403, json={"name": "Forbidden"})
api("Editor", "PATCH", f"customers/{cid}/", json={"notes": "Synthetic verification only"})
api("Editor", "POST", f"customers/{cid}/archive/", json={})
api("Editor", "POST", f"customers/{cid}/restore/", json={})
contact = api("Editor", "POST", "contacts/", 201, json={"full_name": "Synthetic Support Desk", "is_general": True,
    "customer_ids": [cid, second["id"]], "methods": [{"kind": "email", "value": "release@example.invalid"}, {"kind": "phone", "value": "12345678"}]})
api("Editor", "PATCH", f"contacts/{contact['id']}/", 400, json={"methods": []})
api("Editor", "PATCH", f"contacts/{contact['id']}/", json={"job_title": "Rehearsal"})
for action in ("archive", "restore"):
    api("Editor", "POST", f"contacts/{contact['id']}/{action}/", json={})
services = [api("Administrator", "POST", "services/", 201, json={"name": "Release " + secrets.token_hex(4)}) for _ in range(2)]
api("Editor", "POST", "services/", 403, json={"name": "Forbidden"})
for service in services:
    assignment = api("Editor", "POST", "assignments/", 201, json={"customer_id": cid, "service_id": service["id"]})
    api("Editor", "PATCH", f"assignments/{assignment['id']}/", json={"status": "suspended"})
    api("Editor", "PATCH", f"assignments/{assignment['id']}/", json={"status": "active"})
for mode in ("any", "all"):
    params = [("services", item["id"]) for item in services] + [("mode", mode), ("page_size", "1")]
    result = api("Viewer", "GET", "search/by-service/", params=params)
    assert result["count"] == 1
    emails = api("Viewer", "GET", "search/by-service/emails/", params=params)
    assert "release@example.invalid" in str(emails)
api("Viewer", "GET", "search/", params={"q": "release@example.invalid"})
for kind, document in (
    ("customers", {"schema_version": 1, "customers": [{"import_id": "release-import-customer", "name": "Synthetic imported customer"}]}),
    ("contacts", {"schema_version": 1, "contacts": [{"import_id": "release-import-contact", "name": "Synthetic imported contact",
        "customer_import_ids": ["release-import-customer"], "emails": [{"address": "import@example.invalid"}]}]}),
):
    preview = api("Administrator", "POST", f"imports/{kind}/preview/", json={"document": document})
    api("Administrator", "POST", f"imports/{kind}/execute/", json={"confirmation_token": preview["confirmation_token"], "confirm": True})
api("Viewer", "GET", "audit/", 403)
api("Editor", "GET", "cleanup/archived-customers/", 403)
api("Administrator", "GET", "audit/")
removed = api("Administrator", "POST", "customers/", 201, json={"name": "Disposable cleanup target"})
api("Administrator", "POST", f"customers/{removed['id']}/archive/", json={})
preview = api("Administrator", "POST", "cleanup/preview/", json={"customer_ids": [removed["id"]], "contact_ids": []})
api("Administrator", "POST", "cleanup/confirm/", json={"confirmation_token": preview["confirmation_token"], "confirm": True})
assert not Customer.objects.filter(pk=removed["id"]).exists()
# Exercise real session login + CSRF and the main GUI through Caddy.
web = requests.Session()
web.trust_env = False
web.verify = "/tmp/release-ca.crt"
response = web.get(base + "/accounts/login/", timeout=20)
assert response.status_code == 200
response = web.post(base + "/accounts/login/", data={"username": admin.username, "password": password,
    "csrfmiddlewaretoken": web.cookies["csrftoken"]}, headers={"Referer": base + "/accounts/login/"}, timeout=20)
assert response.status_code == 200 and "/accounts/login/" not in response.url
for path in ("/", "/customers/", "/contacts/", "/services/", "/search/", "/search/by-service/", "/audit/", "/api/v1/docs/"):
    assert web.get(base + path, timeout=20).status_code == 200, path
    count += 1
print(f"Verified HTTPS release smoke checks: {count} passed; synthetic business records retained for persistence/restore tests.")
