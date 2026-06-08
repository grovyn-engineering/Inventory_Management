from django.urls import path

from .views import (
    admin_dashboard,
    login_view,
    logout_view,
    manager_dashboard,
    root_view,
    worker_dashboard,
)

urlpatterns = [
    path("", root_view, name="root"),
    path("login", login_view, name="login"),
    path("login/", login_view),
    path("logout", logout_view, name="logout"),
    path("logout/", logout_view),
    path("dashboard/admin/", admin_dashboard, name="dashboard_admin"),
    path("dashboard/manager/", manager_dashboard, name="dashboard_manager"),
    path("dashboard/worker/", worker_dashboard, name="dashboard_worker"),
]
