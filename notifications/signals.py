from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from inventory.models import Stock
from .service import notify_stock_state_change


@receiver(pre_save, sender=Stock)
def capture_previous_stock_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_quantity = None
        instance._previous_expiry_date = None
        return
    previous = Stock.objects.filter(pk=instance.pk).only("quantity", "expiry_date").first()
    if previous is None:
        instance._previous_quantity = None
        instance._previous_expiry_date = None
        return
    instance._previous_quantity = previous.quantity
    instance._previous_expiry_date = previous.expiry_date


@receiver(post_save, sender=Stock)
def trigger_stock_notifications(sender, instance, created, **kwargs):
    notify_stock_state_change(
        instance,
        previous_quantity=getattr(instance, "_previous_quantity", None),
        previous_expiry_date=getattr(instance, "_previous_expiry_date", None),
        created=created,
    )
