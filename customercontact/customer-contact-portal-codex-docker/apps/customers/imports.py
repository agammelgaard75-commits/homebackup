"""Customer JSON preview and transactional upsert through the customer write API."""
import copy
import hashlib
import json
from collections import Counter
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from apps.audit.services import record_import_summary
from apps.core.json_import import import_key

from .models import Customer
from .services import create_customer, update_customer

FIELDS = {"import_id", "name", "company_id", "status", "notes"}


def _signature(customer):
    if customer is None:
        return ""
    values = [str(customer.pk), customer.import_id, customer.name, customer.reference_code,
              customer.status, customer.address, customer.notes, customer.updated_at.isoformat()]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def _errors(error):
    if hasattr(error, "message_dict"):
        return [message for messages in error.message_dict.values() for message in messages]
    return error.messages


def _mapped_customer(value):
    try:
        return Customer.objects.filter(pk=UUID(value)).first()
    except (TypeError, ValueError, AttributeError):
        return None


def preview_customers(payload, mappings=None, separate=None):
    mappings, separate = mappings or {}, set(separate or [])
    records = payload["customers"]
    duplicate_keys = {key for key, count in Counter(record.get("import_id") for record in records
                          if isinstance(record, dict) and isinstance(record.get("import_id"), str)).items() if count > 1}
    rows, used_targets = [], set()
    for index, item in enumerate(records, 1):
        row = {"index": index, "key": "", "name": "", "action": "reject", "errors": [],
               "candidates": [], "target": None, "values": None, "signature": ""}
        rows.append(row)
        if not isinstance(item, dict):
            row["errors"].append("Record must be a JSON object.")
            continue
        key, name = item.get("import_id"), item.get("name")
        row["key"] = key if isinstance(key, str) else ""
        row["name"] = name if isinstance(name, str) else ""
        if set(item) - FIELDS:
            row["errors"].append("Unsupported field in this customer record.")
        if not import_key(key):
            row["errors"].append("import_id must be a stable key of at most 128 permitted characters.")
        elif key in duplicate_keys:
            row["errors"].append("Duplicate import_id in this file.")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
            row["errors"].append("name must contain 1–200 characters.")
        if "company_id" in item and item["company_id"] is not None and not isinstance(item["company_id"], str):
            row["errors"].append("company_id must be a string or null.")
        if "notes" in item and not isinstance(item["notes"], str):
            row["errors"].append("notes must be a string.")
        if "status" in item and item["status"] not in ("active", "inactive", "archived"):
            row["errors"].append("status must be active, inactive or archived.")
        if row["errors"]:
            continue
        existing = Customer.objects.filter(import_id=key).first()
        mapped_id = mappings.get(key, "")
        if mapped_id:
            mapped = _mapped_customer(mapped_id)
            if mapped is None:
                row["errors"].append("Mapped customer UUID does not exist.")
                continue
            if mapped.import_id not in (None, key):
                row["errors"].append("Mapped customer already belongs to another import_id.")
                continue
            if existing and existing.pk != mapped.pk:
                row["errors"].append("This import_id already belongs to another customer.")
                continue
            existing = mapped
        if existing and existing.pk in used_targets:
            row["errors"].append("Multiple import rows target the same customer.")
            continue
        if existing:
            used_targets.add(existing.pk)
            row["target"] = existing
            row["signature"] = _signature(existing)
        values = {
            "name": name.strip(),
            "reference_code": existing.reference_code if existing else "",
            "status": existing.status if existing else Customer.Status.ACTIVE,
            "address": existing.address if existing else "",
            "notes": existing.notes if existing else "",
            "import_id": key,
        }
        if "company_id" in item:
            values["reference_code"] = item["company_id"] or ""
        if "status" in item:
            values["status"] = Customer.Status.INACTIVE if item["status"] == "archived" else item["status"]
        if "notes" in item:
            values["notes"] = item["notes"]
        candidate = copy.copy(existing) if existing else Customer()
        for field, value in values.items():
            setattr(candidate, field, value)
        try:
            candidate.full_clean()
        except ValidationError as error:
            row["errors"].extend(_errors(error))
        values["name"] = candidate.name
        values["reference_code"] = candidate.reference_code
        row["values"] = values
        if not existing:
            candidate_filter = Q(name__iexact=values["name"])
            if values["reference_code"]:
                candidate_filter |= Q(reference_code__iexact=values["reference_code"])
            possible = Customer.objects.filter(candidate_filter).values("pk", "name")[:5]
            row["candidates"] = list(possible)
            if row["candidates"] and key not in separate:
                row["errors"].append("A customer with this name exists. Map its UUID or explicitly approve a separate record.")
        if not row["errors"]:
            row["action"] = ("create" if not existing else "unchanged" if all(
                getattr(existing, field) == value for field, value in values.items()) else "update")
    reference_counts = Counter(row["values"]["reference_code"] for row in rows
                               if row["values"] and row["values"]["reference_code"])
    for row in rows:
        if row["values"] and reference_counts[row["values"]["reference_code"]] > 1:
            row["errors"].append("Duplicate company_id in this file.")
            row["action"] = "reject"
    return rows


def manifest(rows):
    safe = [(row["key"], row["action"], str(row["target"].pk) if row["target"] else "", row["signature"])
            for row in rows]
    return hashlib.sha256(json.dumps(safe).encode()).hexdigest()


@transaction.atomic
def confirm_customers(*, actor, payload, mappings, separate, expected_manifest):
    required = ("accounts.access_portal", "accounts.edit_portal", "accounts.administer_portal",
                "customers.view_customer", "customers.add_customer", "customers.change_customer")
    if not actor.is_active or not actor.has_perms(required):
        raise PermissionDenied
    keys = [item.get("import_id") for item in payload["customers"] if isinstance(item, dict)]
    list(Customer.objects.select_for_update().filter(import_id__in=keys))
    mapped_ids = [value for value in mappings.values() if value]
    list(Customer.objects.select_for_update().filter(pk__in=mapped_ids))
    rows = preview_customers(payload, mappings, separate)
    if any(row["errors"] for row in rows) or manifest(rows) != expected_manifest:
        raise ValidationError("The preview is no longer current. Upload the file and review it again.")
    counts = Counter(row["action"] for row in rows)
    for row in rows:
        if row["action"] == "create":
            create_customer(actor=actor, **row["values"])
        elif row["action"] == "update":
            update_customer(actor=actor, customer_id=row["target"].pk, **row["values"])
    record_import_summary(actor=actor, kind="customers", created=counts["create"],
                          updated=counts["update"], unchanged=counts["unchanged"])
    return counts
