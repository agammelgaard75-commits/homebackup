from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.views import set_rollback
import logging


def portal_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    response = exception_handler(exc, context)
    if response is None:
        # Never return exception messages, submitted values or configuration.
        # Preserve rollback semantics when ATOMIC_REQUESTS is enabled.
        set_rollback()
        logging.getLogger("portal.api").error("Unhandled API failure", exc_info=True)
        return Response({"error": {"code": "server_error", "detail": "The request could not be completed."}}, status=500)
    detail = response.data
    if isinstance(detail, dict) and set(detail) == {"detail"}:
        response.data = {"error": {"code": getattr(exc, "default_code", "error"), "detail": str(detail["detail"])}}
    else:
        response.data = {"error": {"code": "validation_error", "fields": detail}}
    return response
