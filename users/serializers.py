from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from common.validation import StrictSerializer
from inventory.models import Location
from .models import ROLE_MANAGER, ROLE_WORKER

User = get_user_model()


class LoginSerializer(StrictSerializer):
    username = serializers.CharField()
    password = serializers.CharField()


class CreateUserSerializer(StrictSerializer):
    username = serializers.CharField(
        validators=[UniqueValidator(queryset=User.objects.all())],
        required=False,
        allow_blank=True,
    )
    name = serializers.CharField(required=True, allow_blank=False, max_length=150)
    email = serializers.EmailField(required=True, allow_blank=False)
    phone_number = serializers.CharField(
        required=True,
        allow_blank=False,
        validators=[UniqueValidator(queryset=User.objects.exclude(phone_number__isnull=True))],
    )
    password = serializers.CharField()
    confirm_password = serializers.CharField()
    role = serializers.ChoiceField(choices=[ROLE_MANAGER, ROLE_WORKER])
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(),
        source='location',
        required=False,
    )

    def validate(self, attrs):
        phone_number = (attrs.get("phone_number") or "").strip()
        if not phone_number.isdigit():
            raise serializers.ValidationError(
                {"phone_number": ["Phone number must contain digits only."]}
            )
        if not 10 <= len(phone_number) <= 15:
            raise serializers.ValidationError(
                {"phone_number": ["Phone number length must be between 10 and 15 digits."]}
            )
        attrs["phone_number"] = phone_number

        if attrs.get("password") != attrs.get("confirm_password"):
            raise serializers.ValidationError(
                {"confirm_password": ["Password and confirm password must match."]}
            )

        username = (attrs.get("username") or "").strip()
        if not username:
            attrs["username"] = attrs["email"]
        if User.objects.filter(username=attrs["username"]).exists():
            raise serializers.ValidationError(
                {"email": ["A user with this email already exists."]}
            )

        role = attrs.get('role')
        if role in [ROLE_MANAGER, ROLE_WORKER] and 'location' not in attrs:
            raise serializers.ValidationError(
                {"location_id": ["This field is required for the selected role."]}
            )
        return attrs


class DeleteUserParamsSerializer(StrictSerializer):
    user_id = serializers.IntegerField(min_value=1)
