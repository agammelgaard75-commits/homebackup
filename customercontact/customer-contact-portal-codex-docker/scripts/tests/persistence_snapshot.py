"""Value-free row digests for an explicitly disposable release rehearsal."""
import hashlib
import json
import os
import sys
sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
if os.environ.get("ALLOW_DISPOSABLE_SMOKE") != "portal-release-verify":
    raise SystemExit("Only the disposable release rehearsal is authorized.")
result = {}
for model in apps.get_models(include_auto_created=True):
    rows = list(model.objects.order_by(model._meta.pk.name).values())
    encoded = json.dumps(rows, cls=DjangoJSONEncoder, sort_keys=True).encode()
    result[model._meta.label] = {"count": len(rows), "sha256": hashlib.sha256(encoded).hexdigest()}
print(json.dumps(result, sort_keys=True))
