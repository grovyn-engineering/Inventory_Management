from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from common.responses import success_response
from common.validation import BaseQuerySerializer, validate_body, validate_query
from .serializers import CreateOrderSerializer
from . import service as order_service


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_order(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(CreateOrderSerializer, request, context={'user': request.user})

    order_data = order_service.create_order_for_user(
        user=request.user,
        items=data['items'],
        location_id=data.get('location_id'),
    )

    return success_response(
        "Order created successfully",
        data=order_data,
        status=201,
    )
