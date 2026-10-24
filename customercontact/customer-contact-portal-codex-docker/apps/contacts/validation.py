"""Local normalization only; never sends contact information to another service."""
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

PHONE_CHARACTERS = re.compile(r"\A\+?[0-9 () .-]+\Z")


def phone_search_value(value):
    value = value.strip()
    if not PHONE_CHARACTERS.fullmatch(value):
        return ""
    digits = re.sub(r"[^0-9]", "", value)
    return digits[2:] if digits.startswith("00") else digits


def normalize_contact_value(kind, value):
    value = value.strip()
    if kind == "email":
        validate_email(value)
        return value.lower()
    if kind == "phone":
        normalized = phone_search_value(value)
        if not 7 <= len(normalized) <= 15:
            raise ValidationError("Enter 7–15 digits, optionally with a leading + or 00, spaces, parentheses, dots or hyphens.")
        return normalized
    raise ValidationError("Select email or phone.")
