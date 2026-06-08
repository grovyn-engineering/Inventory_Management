from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.responses import success_response
from common.validation import (
    BaseQuerySerializer,
    EmptySerializer,
    validate_body,
    validate_params,
    validate_query,
)
from .serializers import AlertParamsSerializer
from . import service as notification_service


@extend_schema(
    description="List alerts for the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_alerts(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    data = notification_service.get_alerts_for_user(request.user)
    return success_response("Alerts fetched", data=data, status=200)


@extend_schema(
    description="Get unread alert count for the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_count(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    count = notification_service.get_unread_count_for_user(request.user)
    return success_response("Unread count fetched", data={"unread": count}, status=200)


@extend_schema(
    description="Mark an alert as read.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def mark_alert_read(request, alert_id):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    params = validate_params(AlertParamsSerializer, {'alert_id': alert_id})

    notification_service.mark_alert_read_for_user(
        user=request.user,
        alert_id=params['alert_id'],
    )

    return success_response("Alert marked as read", status=200)
