from django.urls import path

from .controllers import create_user, delete_user, list_users, login_view

urlpatterns = [
    path('login/', login_view, name='login'),
    path('create/', create_user, name='create_user'),
    path('list/', list_users, name='list_users'),
    path('delete/<int:user_id>/', delete_user, name='delete_user'),
]
