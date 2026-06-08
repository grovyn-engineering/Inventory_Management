import logging
import traceback

from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    PermissionDenied,
    ParseError,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .responses import build_error_response

logger = logging.getLogger("api.error")


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled DRF exception", extra={"view": str(context.get("view")) if context else None})
        error_message = str(exc) or "Internal server error"
        errors = [{"field": "server", "message": error_message}]
        if settings.DEBUG:
            errors.append({"field": "stack", "message": traceback.format_exc()})
        return Response(
            build_error_response(
                message=error_message,
                errors=errors,
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    status_code, message = _resolve_status_and_message(exc, response.status_code)
    response.status_code = status_code
    response.data = build_error_response(
        message=message,
        errors=_build_errors(exc, response.data),
    )
    return response


def _resolve_status_and_message(exc, default_status_code):
    if isinstance(exc, (InvalidToken, TokenError, NotAuthenticated, AuthenticationFailed)):
        return status.HTTP_401_UNAUTHORIZED, "Authentication failed"
    if isinstance(exc, PermissionDenied):
        return status.HTTP_403_FORBIDDEN, "Permission denied"
    if isinstance(exc, (Http404,)):
        return status.HTTP_404_NOT_FOUND, "Resource not found"
    if isinstance(exc, MethodNotAllowed):
        return status.HTTP_405_METHOD_NOT_ALLOWED, "Method not allowed"
    if isinstance(exc, (ParseError, UnsupportedMediaType)):
        return status.HTTP_400_BAD_REQUEST, "Invalid request"
    if isinstance(exc, ValidationError):
        return status.HTTP_400_BAD_REQUEST, "Validation failed"
    if default_status_code >= 500:
        return default_status_code, str(exc) or "Internal server error"
    return default_status_code, "Request failed"


def _build_errors(exc, detail):
    if isinstance(exc, (InvalidToken, TokenError, NotAuthenticated, AuthenticationFailed)):
        return [{"field": "token", "message": _get_token_error_message(detail, exc)}]
    if detail:
        return detail
    return [{"field": "non_field_errors", "message": str(exc)}]


def _get_token_error_message(detail, exc):
    token_message = _extract_token_message(detail)
    if token_message:
        return token_message
    return str(exc) or "Invalid authentication token."


def _extract_token_message(detail):
    if isinstance(detail, dict):
        if "messages" in detail and isinstance(detail["messages"], list):
            for item in detail["messages"]:
                if isinstance(item, dict):
                    token_message = item.get("message")
                    if token_message:
                        return _normalize_token_message(token_message)
        for value in detail.values():
            token_message = _extract_token_message(value)
            if token_message:
                return token_message
    elif isinstance(detail, (list, tuple)):
        for item in detail:
            token_message = _extract_token_message(item)
            if token_message:
                return token_message
    elif detail:
        return _normalize_token_message(str(detail))
    return None


def _normalize_token_message(message):
    lowered = message.lower()
    if "expired" in lowered:
        return "Token is expired"
    if "invalid" in lowered:
        return "Token is invalid"
    return message
