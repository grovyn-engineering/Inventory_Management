from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from common.responses import error_response, success_response
from common.validation import (
    BaseQuerySerializer,
    EmptySerializer,
    validate_body,
    validate_params,
    validate_query,
)
from .serializers import CreateUserSerializer, DeleteUserParamsSerializer, LoginSerializer
from . import service as user_service


@extend_schema(
    description="Authenticate a user and return JWT tokens.",
    request=LoginSerializer,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(LoginSerializer, request)
    username = data['username']
    password = data['password']

    user = user_service.authenticate_user(username, password)
    if not user:
        return error_response("Invalid credentials", status=401)

    refresh = RefreshToken.for_user(user)
    return success_response(
        "Login successful",
        data={
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "location": user.location.name if user.location else None,
            },
        },
        status=200,
    )


@extend_schema(
    description="Create a user from the admin dashboard.",
    request=CreateUserSerializer,
    responses={201: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_user(request):
    validate_query(BaseQuerySerializer, request)
    data = validate_body(CreateUserSerializer, request)

    user = user_service.create_user_for_admin(
        admin=request.user,
        username=data['username'],
        name=data["name"],
        email=data["email"],
        phone_number=data["phone_number"],
        password=data['password'],
        role=data['role'],
        location=data.get('location'),
    )

    return success_response(
        "User created successfully",
        data={"user_id": user.id},
        status=201,
    )


@extend_schema(
    description="List users visible to the authenticated user.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_users(request):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    data = user_service.list_users_for_user(request.user)
    return success_response("Users fetched", data=data, status=200)


@extend_schema(
    description="Delete a user by id.",
    request=None,
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id):
    validate_query(BaseQuerySerializer, request)
    validate_body(EmptySerializer, request)
    params = validate_params(DeleteUserParamsSerializer, {'user_id': user_id})

    user_service.delete_user_for_admin(
        admin=request.user,
        user_id=params['user_id'],
    )

    return success_response("User deleted successfully", status=200)
