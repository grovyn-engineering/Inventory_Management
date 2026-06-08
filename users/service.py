from django.contrib.auth import authenticate, get_user_model
from django.http import Http404
from rest_framework.exceptions import PermissionDenied

User = get_user_model()


def authenticate_user(username, password):
    return authenticate(username=username, password=password)


def create_user_for_admin(admin, username, name, email, phone_number, password, role, location):
    if not admin.has_role("admin"):
        raise PermissionDenied("Only admin can create users")

    return User.objects.create_user(
        username=username,
        first_name=name,
        email=email,
        phone_number=phone_number,
        password=password,
        role=role,
        location=location
    )


def list_users_for_user(user):
    if user.has_role("admin"):
        users = User.objects.all()
    else:
        users = User.objects.filter(location=user.location)

    return [
        {
            "id": u.id,
            "username": u.username,
            "name": u.first_name,
            "email": u.email,
            "phone_number": u.phone_number,
            "role": u.role,
            "location": u.location.name if u.location else None
        }
        for u in users
    ]


def delete_user_for_admin(admin, user_id):
    if not admin.has_role("admin"):
        raise PermissionDenied("Only admin can delete users")

    user = User.objects.filter(id=user_id).first()
    if not user:
        raise Http404("User not found")

    user.delete()
