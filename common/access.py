from rest_framework.exceptions import PermissionDenied, ValidationError


def require_user_location(user, *, field_name="location"):
    location = getattr(user, "location", None)
    if location is None:
        raise ValidationError({field_name: ["User has no assigned location."]})
    return location


def enforce_location_access(user, location, *, field_name="location_id", allow_admin=True):
    if allow_admin and user.has_role("admin"):
        return location

    user_location = require_user_location(user, field_name=field_name)
    if location != user_location:
        raise PermissionDenied("Unauthorized location access")
    return user_location


def enforce_resource_location(user, resource, *, allow_admin=True):
    resource_location = getattr(resource, "location", None)
    if resource_location is None:
        raise ValidationError({"location": ["Resource is not linked to a location."]})
    return enforce_location_access(user, resource_location, allow_admin=allow_admin)
