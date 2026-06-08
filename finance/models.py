from django.db import models
from django.db.models import Q
from common.models import TimeStampedModel

class Bill(TimeStampedModel):
    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card'),
        ('netbanking', 'Netbanking'),
        ('wallet', 'Wallet'),
    )

    order = models.OneToOneField('orders.Order', on_delete=models.CASCADE, related_name='bill')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_id = models.CharField(max_length=255, null=True, blank=True, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=['payment_method', 'created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_paid__gt=0),
                name='bill_amount_paid_gt_zero',
            ),
        ]
    def __str__(self):
        return f"Bill for Order {self.order.id}"


class Transaction(TimeStampedModel):
    TRANSACTION_TYPE = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )

    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card'),
        ('netbanking', 'Netbanking'),
        ('wallet', 'Wallet'),
    )

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, db_index=True)
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
    )
    location = models.ForeignKey(
        'inventory.Location',
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    description = models.TextField(blank=True, default='')

    class Meta:
        indexes = [
            models.Index(fields=['location', 'created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='transaction_amount_gt_zero',
            ),
        ]
    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"
