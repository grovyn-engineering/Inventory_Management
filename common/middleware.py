import logging
import time
import traceback
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, JsonResponse
from rest_framework.exceptions import ValidationError as DRFValidationError

from .responses import build_error_response

request_logger = logging.getLogger("api.request")
error_logger = logging.getLogger("api.error")


class RequestIdMiddleware:
    header_name = 'X-Request-ID'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = str(uuid.uuid4())

        request.request_id = request_id
        response = self.get_response(request)
        response[self.header_name] = request_id
        return response


class ApiRequestLoggingMiddleware:
    api_prefixes = (
        '/api/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.monotonic()
        response = self.get_response(request)

        if self._is_api_request(request):
            duration_ms = int((time.monotonic() - start_time) * 1000)
            log_extra = _build_log_extra(
                request,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            if response.status_code >= 500:
                error_logger.error("API request failed", extra=log_extra)
            elif response.status_code >= 400:
                error_logger.warning("API request failed", extra=log_extra)
            else:
                request_logger.info("API request", extra=log_extra)

        return response

    def _is_api_request(self, request):
        path = getattr(request, 'path', '')
        return any(path.startswith(prefix) for prefix in self.api_prefixes)


class GlobalErrorHandlerMiddleware:
    api_prefixes = (
        '/api/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except (DRFValidationError, DjangoValidationError) as exc:
            if self._is_api_request(request):
                detail = getattr(exc, 'detail', None)
                if detail is None:
                    if hasattr(exc, 'message_dict'):
                        detail = exc.message_dict
                    elif hasattr(exc, 'messages'):
                        detail = exc.messages
                    else:
                        detail = str(exc)
                error_logger.warning(
                    "Validation error",
                    extra=_build_log_extra(request, status_code=400, error_type="validation", detail=detail),
                )
                return JsonResponse(
                    build_error_response("Validation failed", detail),
                    status=400,
                )
            raise
        except Http404:
            if self._is_api_request(request):
                error_logger.warning(
                    "Not found",
                    extra=_build_log_extra(request, status_code=404, error_type="not_found"),
                )
                return JsonResponse(
                    build_error_response(
                        "Resource not found",
                        [{"field": "resource", "message": "Resource not found"}],
                    ),
                    status=404,
                )
            raise
        except Exception as exc:
            if self._is_api_request(request):
                error_logger.exception(
                    "Unhandled exception",
                    extra=_build_log_extra(
                        request,
                        status_code=500,
                        error_type="server_error",
                        detail=str(exc),
                    ),
                )
                errors = [{"field": "server", "message": str(exc) or "Internal server error"}]
                if settings.DEBUG:
                    errors.append({"field": "stack", "message": traceback.format_exc()})
                return JsonResponse(
                    build_error_response(
                        str(exc) or "Internal server error",
                        errors,
                    ),
                    status=500,
                )
            raise

        if (
            self._is_api_request(request)
            and response.status_code == 404
            and not self._is_formatted_response(response)
        ):
            return JsonResponse(
                build_error_response(
                    "Resource not found",
                    [{"field": "resource", "message": "Resource not found"}],
                ),
                status=404,
            )

        return response

    def _is_api_request(self, request):
        path = getattr(request, 'path', '')
        return any(path.startswith(prefix) for prefix in self.api_prefixes)

    def _is_formatted_response(self, response):
        data = getattr(response, 'data', None)
        if not isinstance(data, dict):
            return False
        return (
            {'success', 'message'}.issubset(set(data.keys()))
            and ('data' in data or 'errors' in data)
        )


class ApiAuthHeaderMiddleware:
    protected_prefixes = (
        '/api/',
    )
    public_paths = {
        '/api/users/login',
        '/api/users/login/',
        '/api/finance/webhook/razorpay',
        '/api/finance/webhook/razorpay/',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'OPTIONS':
            return self.get_response(request)

        if self._is_protected_path(request.path) and not self._is_public_path(request.path):
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                return self.get_response(request)
            if getattr(request, "user", None) is not None and request.user.is_authenticated:
                return self.get_response(request)
            return JsonResponse(
                build_error_response(
                    "Authentication failed",
                    [{"field": "token", "message": "Missing or invalid token"}],
                ),
                status=401,
            )

        return self.get_response(request)

    def _is_protected_path(self, path):
        return any(path.startswith(prefix) for prefix in self.protected_prefixes)

    def _is_public_path(self, path):
        return path in self.public_paths


def _build_log_extra(request, status_code=None, duration_ms=None, error_type=None, detail=None):
    user_id = None
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        user_id = getattr(user, 'id', None)

    request_id = getattr(request, 'request_id', None)
    request_body = None
    try:
        raw_body = getattr(request, "body", b"")
        if raw_body:
            request_body = raw_body.decode("utf-8", errors="replace")
    except Exception:
        request_body = "<unavailable>"

    return {
        "method": getattr(request, 'method', None),
        "path": getattr(request, 'path', None),
        "status_code": status_code,
        "duration_ms": duration_ms,
        "user_id": user_id,
        "ip": request.META.get('REMOTE_ADDR') if hasattr(request, 'META') else None,
        "request_id": request_id,
        "error_type": error_type,
        "detail": detail,
        "request_body": request_body,
    }
