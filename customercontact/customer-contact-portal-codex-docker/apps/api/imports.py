import json
from collections import Counter

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.parsers import BaseParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.contacts.imports import confirm_contacts, manifest as contact_manifest, preview_contacts
from apps.core.json_import import (_reject_constant, _unique_object, open_preview, seal_preview,
                                   validate_document)
from apps.customers.imports import confirm_customers, manifest as customer_manifest, preview_customers
from apps.api.common import require_api
from apps.api.schema import ImportExecuteRequest, ImportExecuteResponse, ImportPreviewRequest, ImportPreviewResponse


class StrictImportJSONParser(BaseParser):
    media_type = "application/json"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read(settings.JSON_IMPORT_MAX_BYTES + 65537)
        if len(raw) > settings.JSON_IMPORT_MAX_BYTES + 65536:
            raise ParseError("JSON import request exceeds the configured size limit.")
        try:
            return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, DjangoValidationError) as error:
            raise ParseError("Enter valid UTF-8 JSON without duplicate keys.") from error


class ImportThrottle(UserRateThrottle):
    rate = "10/min"


def _choices(data):
    mappings = data.get("mappings", {})
    separate = data.get("separate", [])
    if not isinstance(mappings, dict) or any(not isinstance(key, str) or not isinstance(value, str)
                                              for key, value in mappings.items()):
        raise ValidationError({"mappings": ["Use an object of import IDs and existing UUIDs."]})
    if not isinstance(separate, list) or any(not isinstance(key, str) for key in separate):
        raise ValidationError({"separate": ["Use an array of import IDs."]})
    return mappings, set(separate)


def _row_data(row):
    candidates = row["candidates"]
    return {"row": row["index"], "import_id": row["key"], "name": row["name"],
            "action": row["action"], "errors": row["errors"],
            "target_id": str(row["target"].pk) if row["target"] else None,
            "candidate_ids": [str(candidate["pk"] if isinstance(candidate, dict) else candidate.pk)
                              for candidate in candidates]}


class ImportPreviewAPI(APIView):
    serializer_class = ImportPreviewResponse
    parser_classes = [StrictImportJSONParser]
    throttle_classes = [ImportThrottle]
    kind = None

    @extend_schema(request=ImportPreviewRequest, responses=ImportPreviewResponse, examples=[OpenApiExample(
        "Customer import preview", value={"document": {"schema_version": 1, "customers": [
            {"import_id": "customer-example", "name": "Example Company"}]}} , request_only=True)])
    def post(self, request):
        require_api(request, "accounts.edit_portal", "accounts.administer_portal", scope="import")
        if self.kind == "customers":
            require_api(request, "customers.view_customer", "customers.add_customer", "customers.change_customer", scope="import")
            preview, manifest = preview_customers, customer_manifest
        else:
            require_api(request, "customers.view_customer", "contacts.view_contact", "contacts.view_contactpoint",
                        "contacts.add_contact", "contacts.change_contact", "contacts.add_contactpoint",
                        "contacts.change_contactpoint", scope="import")
            preview, manifest = preview_contacts, contact_manifest
        if not isinstance(request.data, dict):
            raise ValidationError({"document": ["Use a JSON object with a document property."]})
        document = validate_document(request.data.get("document"), self.kind)
        if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > settings.JSON_IMPORT_MAX_BYTES:
            raise ValidationError({"document": ["JSON file exceeds the configured size limit."]})
        mappings, separate = _choices(request.data)
        rows = preview(document, mappings, separate)
        counts = Counter(row["action"] for row in rows)
        token = None if counts["reject"] else seal_preview(actor=request.user, kind=self.kind,
            payload=document, mappings=mappings, separate=separate, manifest=manifest(rows))
        return Response({"counts": {action: counts[action] for action in ("create", "update", "unchanged", "reject")},
                         "records": [_row_data(row) for row in rows], "confirmation_token": token})


class ImportExecuteAPI(APIView):
    serializer_class = ImportExecuteResponse
    throttle_classes = [ImportThrottle]
    kind = None

    @extend_schema(request=ImportExecuteRequest, responses=ImportExecuteResponse)
    def post(self, request):
        require_api(request, "accounts.edit_portal", "accounts.administer_portal", scope="import")
        if self.kind == "customers":
            require_api(request, "customers.view_customer", "customers.add_customer", "customers.change_customer", scope="import")
            confirm = confirm_customers
        else:
            require_api(request, "customers.view_customer", "contacts.view_contact", "contacts.view_contactpoint",
                        "contacts.add_contact", "contacts.change_contact", "contacts.add_contactpoint",
                        "contacts.change_contactpoint", scope="import")
            confirm = confirm_contacts
        if not isinstance(request.data, dict) or request.data.get("confirm") is not True:
            raise ValidationError({"confirm": ["Explicit confirmation is required."]})
        token = request.data.get("confirmation_token", "")
        if not isinstance(token, str) or len(token) > 200000:
            raise ValidationError({"confirmation_token": ["Invalid token."]})
        saved = open_preview(token, actor=request.user, kind=self.kind)
        counts = confirm(actor=request.user, payload=saved["payload"], mappings=saved["mappings"],
                         separate=set(saved["separate"]), expected_manifest=saved["manifest"])
        return Response({"counts": {action: counts[action] for action in ("create", "update", "unchanged")}})
