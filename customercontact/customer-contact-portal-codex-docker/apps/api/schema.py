"""OpenAPI-only shapes for responses that are not owned by a business model."""
from rest_framework import serializers
from drf_spectacular.utils import OpenApiParameter

LIST_PARAMETERS = [
    OpenApiParameter("page", int, description="1-based page number."),
    OpenApiParameter("page_size", int, description="Number of items, default 25, maximum 100."),
]


class CurrentUserResponse(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())


class ErrorDetail(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField(required=False)
    fields = serializers.JSONField(required=False)


class ErrorResponse(serializers.Serializer):
    error = ErrorDetail()


class DashboardResponse(serializers.Serializer):
    active_customers = serializers.IntegerField()
    active_contacts = serializers.IntegerField()
    active_assignments = serializers.IntegerField()


class DirectoryRecord(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class DirectoryRow(serializers.Serializer):
    customer = DirectoryRecord()
    contacts = DirectoryRecord(many=True)
    services = DirectoryRecord(many=True)


class DirectoryResponse(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = DirectoryRow(many=True)


class HealthResponse(serializers.Serializer):
    status = serializers.CharField()


class EmailExportResponse(serializers.Serializer):
    count = serializers.IntegerField()
    emails = serializers.ListField(child=serializers.EmailField())
    recipient_field = serializers.CharField()


class SearchResult(serializers.Serializer):
    result_id = serializers.CharField()
    result_kind = serializers.CharField()
    result_title = serializers.CharField()
    result_subtitle = serializers.CharField()
    result_customer_id = serializers.CharField()
    result_customer_name = serializers.CharField()
    result_status = serializers.CharField()
    result_customer_status = serializers.CharField()
    url = serializers.CharField()


class SearchGroup(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = SearchResult(many=True)


class GlobalSearchResponse(serializers.Serializer):
    query = serializers.CharField()
    groups = serializers.DictField(child=SearchGroup())


class ServiceSearchRow(serializers.Serializer):
    row_customer_id = serializers.UUIDField()
    row_contact_id = serializers.UUIDField(allow_null=True)
    row_customer_name = serializers.CharField()
    row_contact_name = serializers.CharField()
    row_customer_status = serializers.CharField()
    row_customer_updated = serializers.DateTimeField()
    contact_type = serializers.CharField()
    job_title = serializers.CharField()
    contact_active = serializers.BooleanField()
    matching_services = serializers.ListField(child=serializers.DictField())
    emails = serializers.ListField(child=serializers.EmailField())
    phones = serializers.ListField(child=serializers.CharField())


class ContactAssociationRequest(serializers.Serializer):
    customer_id = serializers.UUIDField()


class ContactAssociationResponse(serializers.Serializer):
    customer_id = serializers.UUIDField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ImportPreviewRequest(serializers.Serializer):
    document = serializers.JSONField(help_text="Root object conforming to the documented schema_version 1 customer or contact JSON schema.")
    mappings = serializers.DictField(child=serializers.UUIDField(), required=False)
    separate = serializers.ListField(child=serializers.CharField(), required=False)


class ImportExecuteRequest(serializers.Serializer):
    confirmation_token = serializers.CharField()
    confirm = serializers.BooleanField()


class ImportCounts(serializers.Serializer):
    create = serializers.IntegerField()
    update = serializers.IntegerField()
    unchanged = serializers.IntegerField()
    reject = serializers.IntegerField(required=False)


class ImportRecord(serializers.Serializer):
    row = serializers.IntegerField()
    import_id = serializers.CharField()
    name = serializers.CharField()
    action = serializers.CharField()
    errors = serializers.ListField(child=serializers.CharField())
    target_id = serializers.UUIDField(allow_null=True)
    candidate_ids = serializers.ListField(child=serializers.UUIDField())


class ImportPreviewResponse(serializers.Serializer):
    counts = ImportCounts()
    records = ImportRecord(many=True)
    confirmation_token = serializers.CharField(allow_null=True)


class ImportExecuteResponse(serializers.Serializer):
    counts = ImportCounts()


class CleanupSelection(serializers.Serializer):
    customer_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    contact_ids = serializers.ListField(child=serializers.UUIDField(), required=False)


class CleanupConfirmation(serializers.Serializer):
    confirmation_token = serializers.CharField()
    confirm = serializers.BooleanField()


class CleanupPreviewResponse(serializers.Serializer):
    plan = serializers.JSONField(help_text="Exact record IDs, detachment counts, preserved records, blockers, and state fingerprint.")
    confirmation_ref = serializers.UUIDField()
    confirmation_token = serializers.CharField(allow_null=True)


class CleanupOperationResponse(serializers.Serializer):
    id = serializers.UUIDField()
    confirmation_ref = serializers.UUIDField()
    result = serializers.ChoiceField(choices=["completed", "failed"])
    counts = serializers.JSONField()
    actor_id = serializers.IntegerField(required=False)
    created_at = serializers.DateTimeField(required=False)
    customer_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    contact_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    error_code = serializers.CharField(required=False)


class CredentialIssueResponse(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    user = serializers.IntegerField()
    scopes = serializers.ListField(child=serializers.CharField())
    created_at = serializers.DateTimeField()
    rotated_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)
    token = serializers.CharField(required=False, help_text="Shown once on issuance or rotation; store securely.")
