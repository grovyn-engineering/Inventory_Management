from django.db import models
from django.db.models import Q
from common.models import TimeStampedModel


class Order(TimeStampedModel):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )
    PAYMENT_METHODS = (
        ('cash', 'Cash on Delivery'),
        ('upi', 'UPI'),
        ('card', 'Card'),
        ('netbanking', 'Net Banking'),
        ('wallet', 'Wallet'),
    )

    location = models.ForeignKey(
        'inventory.Location',
        on_delete=models.CASCADE,
        related_name='orders',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    razorpay_order_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['location', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_amount__gte=0),
                name='order_total_amount_gte_zero',
            ),
        ]
    def calculate_total(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_amount = total
        self.save()

    def __str__(self):
        return f"Order #{self.id} - {self.location.name}"


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.CASCADE,
        related_name='order_items',
    )
    variant = models.ForeignKey(
        "inventory.ProductVariant",
        on_delete=models.SET_NULL,
        related_name="order_items",
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name='order_item_quantity_gt_zero',
            ),
            models.UniqueConstraint(
                fields=['order', 'product', 'variant'],
                name='unique_order_item_product_variant_per_order',
            ),
        ]
        indexes = [
            models.Index(fields=['product']),
        ]

    @property
    def subtotal(self):
        return self.quantity * self.price

    def __str__(self):
        if self.variant_id:
            return f"{self.product.name} ({self.variant.name}) x {self.quantity}"
        return f"{self.product.name} x {self.quantity}"
