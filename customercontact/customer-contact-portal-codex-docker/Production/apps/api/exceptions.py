from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def portal_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    response = exception_handler(exc, context)
    if response is None:
        return None
    detail = response.data
    if isinstance(detail, dict) and set(detail) == {"detail"}:
        response.data = {"error": {"code": getattr(exc, "default_code", "error"), "detail": str(detail["detail"])}}
    else:
        response.data = {"error": {"code": "validation_error", "fields": detail}}
    return response
