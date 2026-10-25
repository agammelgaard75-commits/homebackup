"""Contact JSON preview and additive transactional import through contact services."""
import copy
import hashlib
import json
from collections import Counter
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.audit.services import record_import_summary
from apps.core.json_import import import_key
from apps.customers.models import Customer

from .models import Contact, ContactCustomer, ContactPoint
from .selectors import active_customer_ids
from .services import (create_contact, save_contact_point, set_contact_active,
                       set_contact_customers, set_point_active, update_contact)
from .validation import normalize_contact_value

FIELDS = {"import_id", "name", "kind", "job_title", "department", "contact_type", "status",
          "notes", "customer_import_ids", "emails", "phones"}
LABELS = set(ContactPoint.Label.values)
TYPES = set(Contact.Type.values)


def _signature(contact):
    if contact is None:
        return ""
    values = [str(contact.pk), contact.import_id, contact.full_name, contact.job_title,
              contact.department, contact.contact_type, contact.is_general, contact.notes,
              contact.is_active, contact.updated_at.isoformat(),
              list(ContactCustomer.objects.filter(contact=contact).order_by("customer_id").values_list(
                  "customer_id", "is_active", "updated_at")),
              list(ContactPoint.objects.filter(contact=contact).order_by("id").values_list(
                  "id", "kind", "normalized_value", "value", "label", "is_primary", "is_active", "updated_at"))]
    return hashlib.sha256(json.dumps(values, default=str).encode()).hexdigest()


def _mapped_contact(value):
    try:
        return Contact.objects.filter(pk=UUID(value)).first()
    except (TypeError, ValueError, AttributeError):
        return None


def _model_errors(error):
    if hasattr(error, "message_dict"):
        return [message for messages in error.message_dict.values() for message in messages]
    return error.messages


def _methods(item, errors):
    parsed, seen, primary_counts = [], set(), Counter()
    for field, kind, value_name in (("emails", "email", "address"), ("phones", "phone", "number")):
        values = item.get(field, [])
        if not isinstance(values, list):
            errors.append(f"{field} must be an array.")
            continue
        for number, method in enumerate(values, 1):
            if not isinstance(method, dict) or set(method) - {value_name, "label", "primary"}:
                errors.append(f"{field} item {number} has unsupported fields or is not an object.")
                continue
            value = method.get(value_name)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 254:
                errors.append(f"{field} item {number} needs a nonblank value of at most 254 characters.")
                continue
            try:
                normalized = normalize_contact_value(kind, value)
            except ValidationError:
                errors.append(f"{field} item {number} has an invalid email address or phone number.")
                continue
            label = method.get("label", "other")
            if not isinstance(label, str) or label not in LABELS:
                errors.append(f"{field} item {number} has an unsupported label.")
            primary = method.get("primary")
            if primary is not None and type(primary) is not bool:
                errors.append(f"{field} item {number} primary must be true or false.")
            if primary is True:
                primary_counts[kind] += 1
            identity = kind, normalized
            if identity in seen:
                errors.append(f"Duplicate normalized {kind} in this contact.")
            seen.add(identity)
            parsed.append({"kind": kind, "value": value.strip(), "normalized": normalized,
                           "label": label, "label_explicit": "label" in method, "primary": primary})
    if not parsed:
        errors.append("At least one email address or phone number is required.")
    for kind, count in primary_counts.items():
        if count > 1:
            errors.append(f"Only one primary {kind} is allowed.")
    return parsed


def _plan_methods(contact, methods):
    existing = list(ContactPoint.objects.filter(contact=contact)) if contact else []
    by_value = {}
    for point in existing:
        by_value.setdefault((point.kind, point.normalized_value), point)
    current_primaries = {point.kind for point in existing if point.is_active and point.is_primary}
    explicit_primary = {method["kind"] for method in methods if method["primary"] is True}
    planned = []
    for method in methods:
        point = by_value.get((method["kind"], method["normalized"]))
        primary = method["primary"]
        if primary is None:
            primary = bool(point and point.is_active and point.is_primary
                           and method["kind"] not in explicit_primary)
            if not primary and method["kind"] not in current_primaries | explicit_primary:
                primary = True
                current_primaries.add(method["kind"])
        label = method["label"] if method["label_explicit"] or not point else point.label
        operation = "create" if not point else "restore" if not point.is_active else "unchanged"
        if point and point.is_active and (point.label != label or point.is_primary != primary):
            operation = "update"
        if point and not point.is_active and (point.label != label or primary):
            operation = "restore_update"
        planned.append({"kind": method["kind"], "value": point.value if point else method["value"],
                        "label": label, "is_primary": primary, "operation": operation, "point": point})
    return planned


def preview_contacts(payload, mappings=None, separate=None):
    mappings, separate = mappings or {}, set(separate or [])
    records = payload["contacts"]
    duplicate_keys = {key for key, count in Counter(record.get("import_id") for record in records
                          if isinstance(record, dict) and isinstance(record.get("import_id"), str)).items() if count > 1}
    rows, used_targets = [], set()
    for index, item in enumerate(records, 1):
        row = {"index": index, "key": "", "name": "", "action": "reject", "errors": [],
               "candidates": [], "target": None, "values": None, "methods": [],
               "customer_ids": [], "signature": ""}
        rows.append(row)
        if not isinstance(item, dict):
            row["errors"].append("Record must be a JSON object.")
            continue
        key, name = item.get("import_id"), item.get("name")
        row["key"] = key if isinstance(key, str) else ""
        row["name"] = name if isinstance(name, str) else ""
        if set(item) - FIELDS:
            row["errors"].append("Unsupported field in this contact record.")
        if not import_key(key):
            row["errors"].append("import_id must be a stable key of at most 128 permitted characters.")
        elif key in duplicate_keys:
            row["errors"].append("Duplicate import_id in this file.")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200:
            row["errors"].append("name must contain 1–200 characters.")
        for field, limit in (("job_title", 200), ("department", 200), ("notes", 10000)):
            if field in item and (not isinstance(item[field], str) or len(item[field]) > limit):
                row["errors"].append(f"{field} must be a string of at most {limit} characters.")
        if "kind" in item and item["kind"] not in ("person", "general"):
            row["errors"].append("kind must be person or general.")
        if "contact_type" in item and (not isinstance(item["contact_type"], str)
                                        or item["contact_type"] not in TYPES):
            row["errors"].append("Unsupported contact_type.")
        if "status" in item and item["status"] not in ("active", "archived"):
            row["errors"].append("status must be active or archived.")
        references = item.get("customer_import_ids")
        if not isinstance(references, list) or not references:
            row["errors"].append("customer_import_ids must be a nonempty array.")
            references = []
        elif len(references) != len(set(value for value in references if isinstance(value, str))) or any(
            not import_key(value) for value in references):
            row["errors"].append("customer_import_ids must contain distinct valid import keys.")
            references = []
        customers = {customer.import_id: customer for customer in Customer.objects.filter(import_id__in=references)}
        for reference in references:
            if reference not in customers:
                row["errors"].append(f"Unknown customer import_id: {reference}.")
        row["customer_ids"] = [customers[value].pk for value in references if value in customers]
        methods = _methods(item, row["errors"])
        if row["errors"]:
            continue
        existing = Contact.objects.filter(import_id=key).first()
        mapped_id = mappings.get(key, "")
        if mapped_id:
            mapped = _mapped_contact(mapped_id)
            if mapped is None:
                row["errors"].append("Mapped contact UUID does not exist.")
                continue
            if mapped.import_id not in (None, key):
                row["errors"].append("Mapped contact already belongs to another import_id.")
                continue
            if existing and existing.pk != mapped.pk:
                row["errors"].append("This import_id already belongs to another contact.")
                continue
            existing = mapped
        if existing and existing.pk in used_targets:
            row["errors"].append("Multiple import rows target the same contact.")
            continue
        if existing:
            used_targets.add(existing.pk)
            row["target"] = existing
            row["signature"] = _signature(existing)
            if not active_customer_ids(existing):
                row["errors"].append("This contact has no active customer association and cannot be updated by the import service.")
                continue
        values = {
            "full_name": name.strip(), "job_title": existing.job_title if existing else "",
            "department": existing.department if existing else "",
            "contact_type": existing.contact_type if existing else Contact.Type.TECHNICAL,
            "is_general": existing.is_general if existing else False,
            "notes": existing.notes if existing else "", "import_id": key,
            "is_active": existing.is_active if existing else True,
        }
        for field in ("job_title", "department", "contact_type", "notes"):
            if field in item:
                values[field] = item[field]
        if "kind" in item:
            values["is_general"] = item["kind"] == "general"
        if "status" in item:
            values["is_active"] = item["status"] == "active"
        candidate = copy.copy(existing) if existing else Contact(customer_id=row["customer_ids"][0])
        for field, value in values.items():
            setattr(candidate, field, value)
        try:
            candidate.full_clean()
        except ValidationError as error:
            row["errors"].extend(_model_errors(error))
        values["full_name"] = candidate.full_name
        row["values"] = values
        row["methods"] = _plan_methods(existing, methods)
        active_ids = set(active_customer_ids(existing)) if existing else set()
        added_links = set(row["customer_ids"]) - active_ids
        if not existing:
            possible_ids = set(Contact.objects.filter(full_name__iexact=values["full_name"]).values_list("pk", flat=True)[:5])
            method_emails = [method["normalized"] for method in methods if method["kind"] == "email"]
            possible_ids.update(ContactPoint.objects.filter(
                kind="email", normalized_value__in=method_emails,
            ).values_list("contact_id", flat=True)[:5])
            row["candidates"] = list(Contact.objects.filter(pk__in=possible_ids).order_by("full_name")[:5])
            if row["candidates"] and key not in separate:
                row["errors"].append("A contact with this name or email exists. Map its UUID or explicitly approve a separate record.")
        if not row["errors"]:
            scalar_changed = existing and any(getattr(existing, field) != value for field, value in values.items())
            method_changed = any(method["operation"] != "unchanged" for method in row["methods"])
            row["action"] = "create" if not existing else "update" if scalar_changed or method_changed or added_links else "unchanged"
    return rows


def manifest(rows):
    safe = [(row["key"], row["action"], str(row["target"].pk) if row["target"] else "", row["signature"])
            for row in rows]
    return hashlib.sha256(json.dumps(safe).encode()).hexdigest()


@transaction.atomic
def confirm_contacts(*, actor, payload, mappings, separate, expected_manifest):
    required = ("accounts.access_portal", "accounts.edit_portal", "accounts.administer_portal",
                "customers.view_customer", "contacts.view_contact", "contacts.view_contactpoint",
                "contacts.add_contact", "contacts.change_contact", "contacts.add_contactpoint",
                "contacts.change_contactpoint")
    if not actor.is_active or not actor.has_perms(required):
        raise PermissionDenied
    keys = [item.get("import_id") for item in payload["contacts"] if isinstance(item, dict)]
    list(Contact.objects.select_for_update().filter(import_id__in=keys))
    list(Contact.objects.select_for_update().filter(pk__in=[value for value in mappings.values() if value]))
    rows = preview_contacts(payload, mappings, separate)
    if any(row["errors"] for row in rows) or manifest(rows) != expected_manifest:
        raise ValidationError("The preview is no longer current. Upload the file and review it again.")
    counts = Counter(row["action"] for row in rows)
    for row in rows:
        values = dict(row["values"])
        active = values.pop("is_active")
        customer_ids = row["customer_ids"]
        if row["action"] == "create":
            contact = create_contact(actor=actor, customer_id=customer_ids[0], customer_ids=customer_ids,
                methods=[{key: method[key] for key in ("kind", "value", "label", "is_primary")}
                         for method in row["methods"]], **values)
            if not active:
                set_contact_active(actor=actor, customer_id=customer_ids[0], contact_id=contact.pk, is_active=False)
        elif row["action"] == "update":
            contact = row["target"]
            owner_id = active_customer_ids(contact)[0]
            for method in row["methods"]:
                point = method["point"]
                operation = method["operation"]
                if operation.startswith("restore"):
                    set_point_active(actor=actor, customer_id=owner_id, contact_id=contact.pk,
                                     point_id=point.pk, is_active=True)
                if operation in ("create", "update", "restore_update"):
                    save_contact_point(actor=actor, customer_id=owner_id, contact_id=contact.pk,
                                       point_id=point.pk if point else None, kind=method["kind"],
                                       value=method["value"], label=method["label"], is_primary=method["is_primary"])
            update_contact(actor=actor, customer_id=owner_id, contact_id=contact.pk, methods=None, **values)
            union = set(active_customer_ids(contact)) | set(customer_ids)
            if union != set(active_customer_ids(contact)):
                set_contact_customers(actor=actor, customer_id=owner_id, contact_id=contact.pk, customer_ids=union)
            if contact.is_active != active:
                set_contact_active(actor=actor, customer_id=owner_id, contact_id=contact.pk, is_active=active)
    record_import_summary(actor=actor, kind="contacts", created=counts["create"],
                          updated=counts["update"], unchanged=counts["unchanged"])
    return counts
