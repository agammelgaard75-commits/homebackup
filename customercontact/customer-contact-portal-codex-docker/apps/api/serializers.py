from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from django.db.models import Prefetch
from rest_framework import serializers

from apps.accounts.models import APICredential
from apps.audit.models import AuditEvent
from apps.contacts.models import Contact, ContactCustomer, ContactPoint
from apps.contacts.validation import normalize_contact_value
from apps.customers.models import Customer
from apps.services.models import CustomerService, Service


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ("id", "import_id", "name", "reference_code", "status", "address", "notes", "created_at", "updated_at")
        read_only_fields = ("id", "import_id", "created_at", "updated_at")


class ContactPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactPoint
        fields = ("id", "kind", "label", "value", "is_primary", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "is_active", "created_at", "updated_at")


class MethodWriteSerializer(serializers.Serializer):
    point_id = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(choices=ContactPoint.Kind.choices, required=False)
    value = serializers.CharField(max_length=254, required=False, allow_blank=True)
    label = serializers.ChoiceField(choices=ContactPoint.Label.choices, required=False, default=ContactPoint.Label.OTHER)
    is_primary = serializers.BooleanField(default=False)
    remove = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs.get("remove"):
            if not attrs.get("point_id"):
                raise serializers.ValidationError({"point_id": "Required to archive a method."})
            return attrs
        if not attrs.get("kind") or not attrs.get("value", "").strip():
            raise serializers.ValidationError("Choose an email or phone and enter its value.")
        try:
            normalize_contact_value(attrs["kind"], attrs["value"])
        except DjangoValidationError as error:
            raise serializers.ValidationError({"value": error.messages}) from error
        return attrs


class ContactSerializer(serializers.ModelSerializer):
    customer_ids = serializers.SerializerMethodField()
    methods = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = ("id", "import_id", "full_name", "job_title", "department", "contact_type", "is_general",
                  "notes", "is_active", "customer_ids", "methods", "created_at", "updated_at")

    @extend_schema_field(serializers.ListField(child=serializers.UUIDField()))
    def get_customer_ids(self, obj):
        links = getattr(obj, "active_links_for_api", None)
        if links is None:
            links = ContactCustomer.objects.filter(contact=obj, is_active=True)
        return [str(link.customer_id) for link in links]

    @extend_schema_field(ContactPointSerializer(many=True))
    def get_methods(self, obj):
        points = getattr(obj, "points_for_api", None)
        if points is None:
            points = obj.points.filter(is_active=True)
        return ContactPointSerializer(points, many=True).data


def api_contacts(records):
    """Prefetch the same active contact data used by every API representation."""
    return records.prefetch_related(None).prefetch_related(
        Prefetch("points", queryset=ContactPoint.objects.filter(is_active=True), to_attr="points_for_api"),
        Prefetch("customer_links", queryset=ContactCustomer.objects.filter(is_active=True),
                 to_attr="active_links_for_api"),
    )


class ContactWriteSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200)
    job_title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    department = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    contact_type = serializers.ChoiceField(choices=Contact.Type.choices, required=False, default=Contact.Type.TECHNICAL)
    is_general = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(max_length=10000, required=False, allow_blank=True, default="")
    customer_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, required=False)
    methods = MethodWriteSerializer(many=True, required=False)


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ("id", "name", "description", "category", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "is_active", "created_at", "updated_at")


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerService
        fields = ("id", "customer", "service", "status", "start_date", "end_date", "notes", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class CredentialSerializer(serializers.ModelSerializer):
    class Meta:
        model = APICredential
        fields = ("id", "name", "user", "scopes", "created_at", "rotated_at", "expires_at", "revoked_at")
        read_only_fields = fields


class CredentialCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=100)
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=[(scope, scope) for scope in
        ("read", "write", "import", "audit", "cleanup")]), allow_empty=False)
    expires_at = serializers.DateTimeField()


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ("id", "created_at", "actor", "action", "object_type", "object_id", "customer",
                  "related_customer_id", "description", "changed_fields")
