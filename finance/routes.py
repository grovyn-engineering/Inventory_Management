from django.urls import path

from .controllers import location_revenue, razorpay_webhook, refund_order

urlpatterns = [
    path('webhook/razorpay/', razorpay_webhook),
    path('refund/', refund_order),
    path('revenue/<int:location_id>/', location_revenue),
]
