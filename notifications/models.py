from django.db import models
from django.conf import settings
from common.models import TimeStampedModel


class Alert(TimeStampedModel):

    ALERT_TYPE_CHOICES = (
        ('low_stock', 'Low Stock'),
        ('stock_update', 'Stock Update'),
        ('zero_stock', 'Zero Stock'),
        ('expiry', 'Expiry'),
        ('flagged', 'Flagged'),
        ('payment', 'Payment'),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='alerts',
    )
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES, db_index=True)

    message = models.TextField()
    reference_id = models.IntegerField(null=True, blank=True)
    event_key = models.CharField(max_length=160, blank=True, default="", db_index=True)
    location = models.ForeignKey(
        'inventory.Location',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alerts',
    )

    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['alert_type']),
            models.Index(fields=['location', 'created_at']),
            models.Index(fields=['user', 'alert_type', 'event_key']),
        ]

    def __str__(self):
        return f"{self.alert_type} - {self.user.username}"
