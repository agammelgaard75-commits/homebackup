"""Shared upload and signed-preview mechanics; business rules stay in owning apps."""
import json
import re
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import FileResponse, Http404

IMPORT_ID_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
PREVIEW_SALT = "customer-portal-json-import-v1"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("Duplicate JSON object key.")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValidationError("Non-finite JSON numbers are not allowed.")


def parse_upload(upload, collection):
    if not upload or not upload.name.lower().endswith(".json"):
        raise ValidationError("Choose a .json file.")
    if upload.size > settings.JSON_IMPORT_MAX_BYTES:
        raise ValidationError("JSON file exceeds the configured size limit.")
    raw = upload.read(settings.JSON_IMPORT_MAX_BYTES + 1)
    if len(raw) > settings.JSON_IMPORT_MAX_BYTES:
        raise ValidationError("JSON file exceeds the configured size limit.")
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError("Enter valid UTF-8 JSON.") from error
    if not isinstance(document, dict) or set(document) != {"schema_version", collection}:
        raise ValidationError(f"The root must contain only schema_version and {collection}.")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValidationError("Only schema_version 1 is supported.")
    records = document[collection]
    if not isinstance(records, list) or not records:
        raise ValidationError(f"{collection} must be a nonempty array.")
    if len(records) > settings.JSON_IMPORT_MAX_RECORDS:
        raise ValidationError("JSON file exceeds the configured record limit.")
    return document


def import_key(value):
    return isinstance(value, str) and IMPORT_ID_PATTERN.fullmatch(value) is not None


def seal_preview(*, actor, kind, payload, mappings=None, separate=None, manifest=None):
    return signing.dumps({"actor": str(actor.pk), "kind": kind, "payload": payload,
                          "mappings": mappings or {}, "separate": sorted(separate or []),
                          "manifest": manifest}, salt=PREVIEW_SALT, compress=True)


def open_preview(token, *, actor, kind):
    try:
        data = signing.loads(token, salt=PREVIEW_SALT, max_age=1800)
    except (signing.BadSignature, signing.SignatureExpired) as error:
        raise ValidationError("The preview expired or changed. Upload the file again.") from error
    if not isinstance(data, dict) or data.get("actor") != str(actor.pk) or data.get("kind") != kind:
        raise ValidationError("This preview belongs to another user or import screen.")
    return data


def import_workflow(request, *, kind, preview, manifest, confirm):
    """Return render context, HTTP status, and counts after a confirmed import."""
    context = {"previewed": False, "rows": [], "counts": Counter(), "max_bytes": settings.JSON_IMPORT_MAX_BYTES,
               "max_records": settings.JSON_IMPORT_MAX_RECORDS}
    if request.method != "POST":
        return context, 200, None
    action = request.POST.get("action")
    try:
        if action == "preview":
            payload = parse_upload(request.FILES.get("file"), kind)
            mappings, separate = {}, set()
        elif action in ("review", "confirm"):
            token = request.POST.get("draft_token" if action == "review" else "confirm_token", "")
            saved = open_preview(token, actor=request.user, kind=kind)
            payload = saved["payload"]
            if action == "confirm":
                if request.POST.get("confirm_import") != "on":
                    raise ValidationError("Confirm that you reviewed this import before applying it.")
                counts = confirm(actor=request.user, payload=payload, mappings=saved["mappings"],
                                 separate=set(saved["separate"]), expected_manifest=saved["manifest"])
                return context, 200, counts
            mappings = {
                item.get("import_id"): request.POST.get(f"map_{index}", "").strip()
                for index, item in enumerate(payload[kind], 1)
                if isinstance(item, dict) and import_key(item.get("import_id"))
            }
            separate = {
                item.get("import_id") for index, item in enumerate(payload[kind], 1)
                if isinstance(item, dict) and request.POST.get(f"separate_{index}") == "on"
                and import_key(item.get("import_id"))
            }
        else:
            raise ValidationError("Choose a JSON file to preview first.")
        rows = preview(payload, mappings, separate)
        counts = Counter(row["action"] for row in rows)
        for row in rows:
            row["mapping"] = mappings.get(row["key"], "")
            row["separate"] = row["key"] in separate
        context.update(previewed=True, rows=rows, counts=counts,
                       draft_token=seal_preview(actor=request.user, kind=kind, payload=payload,
                                                mappings=mappings, separate=separate))
        if not counts["reject"]:
            context["confirm_token"] = seal_preview(actor=request.user, kind=kind, payload=payload,
                mappings=mappings, separate=separate, manifest=manifest(rows))
        return context, 200, None
    except ValidationError as error:
        context["upload_error"] = "; ".join(error.messages)
        return context, 400, None
    except IntegrityError:
        context["upload_error"] = "A record changed while importing. Upload the file and review it again."
        return context, 409, None


def import_reference(kind, asset):
    files = {
        "customers": {"example": "examples/customers.example.json", "schema": "schemas/customers.schema.json"},
        "contacts": {"example": "examples/contacts.example.json", "schema": "schemas/contacts.schema.json"},
    }
    if kind not in files or asset not in ("example", "schema", "guide"):
        raise Http404
    relative = "docs/JSON_IMPORT_FORMAT.md" if asset == "guide" else files[kind][asset]
    path = Path(settings.BASE_DIR) / relative
    return FileResponse(path.open("rb"), content_type="text/markdown; charset=utf-8" if asset == "guide"
                        else "application/json; charset=utf-8", as_attachment=asset != "guide",
                        filename=path.name)
