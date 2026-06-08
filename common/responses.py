from django.http import JsonResponse
from rest_framework.response import Response

_UNSET = object()


def normalize_errors(errors):
    normalized = []
    _collect_errors(errors, normalized)
    return normalized


def build_success_response(message="", data=_UNSET):
    return {
        "success": True,
        "message": message,
        "data": {} if data is _UNSET else data,
    }


def build_error_response(message="", errors=None):
    return {
        "success": False,
        "message": message,
        "errors": normalize_errors(errors or []),
    }


def success_response(message="", data=_UNSET, status=200):
    return Response(build_success_response(message=message, data=data), status=status)


def error_response(message="", errors=None, status=400):
    payload_errors = errors
    if payload_errors is None:
        payload_errors = [{"field": "non_field_errors", "message": message}]
    return Response(build_error_response(message=message, errors=payload_errors), status=status)


def success_json_response(message="", data=_UNSET, status=200):
    return JsonResponse(build_success_response(message=message, data=data), status=status)


def error_json_response(message="", errors=None, status=400):
    payload_errors = errors
    if payload_errors is None:
        payload_errors = [{"field": "non_field_errors", "message": message}]
    return JsonResponse(build_error_response(message=message, errors=payload_errors), status=status)


def _collect_errors(detail, normalized, field=None):
    if detail is None:
        return

    if isinstance(detail, dict):
        if set(detail.keys()) == {"field", "message"}:
            normalized.append(
                {
                    "field": str(detail["field"]),
                    "message": str(detail["message"]),
                }
            )
            return
        for key, value in detail.items():
            next_field = key if key not in {"detail", "non_field_errors"} else field or "non_field_errors"
            _collect_errors(value, normalized, next_field)
        return

    if isinstance(detail, (list, tuple)):
        for item in detail:
            _collect_errors(item, normalized, field)
        return

    normalized.append(
        {
            "field": field or "non_field_errors",
            "message": str(detail),
        }
    )
