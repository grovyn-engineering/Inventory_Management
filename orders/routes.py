from django.urls import path

from .views import create_order, order_detail, remove_cart_item, sync_cart, verify_payment

urlpatterns = [
    path('create-order/', create_order),
    path('verify-payment/', verify_payment),
    path('manage/<int:order_id>/', order_detail),
    path('cart/sync/', sync_cart),
    path('cart/remove-item/', remove_cart_item),
]
