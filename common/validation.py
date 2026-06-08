import re
from decimal import Decimal

from rest_framework import serializers

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,'&()/-]*$")


class StrictSerializer(serializers.Serializer):
    allow_unknown_fields = False

    def to_internal_value(self, data):
        _sanitize_value(data)
        if not self.allow_unknown_fields and hasattr(data, 'keys'):
            unknown_fields = set(data.keys()) - set(self.fields.keys())
            if unknown_fields:
                unknown_list = ', '.join(sorted(unknown_fields))
                raise serializers.ValidationError(
                    {"non_field_errors": [f"Unexpected field(s): {unknown_list}."]}
                )
        return super().to_internal_value(data)


class EmptySerializer(StrictSerializer):
    pass


class BaseQuerySerializer(StrictSerializer):
    format = serializers.CharField(required=False)


def _sanitize_value(value):
    if isinstance(value, str):
        if '\x00' in value:
            raise serializers.ValidationError(
                {"non_field_errors": ["Invalid characters in input."]}
            )
        return
    if hasattr(value, 'items'):
        for item in value.values():
            _sanitize_value(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _sanitize_value(item)


def validate_serializer(serializer_class, data, *, context=None, partial=False):
    serializer = serializer_class(data=data, context=context or {}, partial=partial)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def validate_body(serializer_class, request, *, context=None, partial=False):
    request_context = {"request": request}
    if context:
        request_context.update(context)
    return validate_serializer(
        serializer_class,
        request.data,
        context=request_context,
        partial=partial,
    )


def validate_query(serializer_class, request, *, context=None, partial=False):
    request_context = {"request": request}
    if context:
        request_context.update(context)
    return validate_serializer(
        serializer_class,
        request.query_params,
        context=request_context,
        partial=partial,
    )


def validate_params(serializer_class, params, *, context=None, partial=False):
    return validate_serializer(serializer_class, params, context=context, partial=partial)


def validate_human_readable_name(value, *, field_label="Name"):
    value = (value or "").strip()
    if not value:
        raise serializers.ValidationError(f"{field_label} cannot be blank.")
    if not NAME_PATTERN.fullmatch(value):
        raise serializers.ValidationError(
            f"{field_label} contains invalid characters."
        )
    return value


def validate_positive_decimal(value, *, field_label="Value"):
    if value is None:
        raise serializers.ValidationError(f"{field_label} is required.")
    if Decimal(value) <= 0:
        raise serializers.ValidationError(f"{field_label} must be greater than zero.")
    return value
