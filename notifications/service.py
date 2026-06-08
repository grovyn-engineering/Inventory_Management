import json
import logging
from datetime import date, timedelta
from urllib import error, request

from django.conf import settings
from django.core.mail import send_mail
from django.http import Http404
from django.db.models import Q

from inventory.models import Stock
from users.models import ROLE_ADMIN, ROLE_MANAGER, User
from .models import Alert

logger = logging.getLogger(__name__)


def _get_low_stock_threshold():
    return int(getattr(settings, "LOW_STOCK_THRESHOLD", 5))


def _get_expiry_alert_days():
    return int(getattr(settings, "EXPIRY_ALERT_DAYS", 2))


def _get_whatsapp_timeout():
    return int(getattr(settings, "WHATSAPP_TIMEOUT_SECONDS", 8))


def _build_stock_item_name(stock):
    if stock.variant_id:
        return f"{stock.product.name} - {stock.variant.name}"
    return stock.product.name


def _detect_flagged_or_thumbs_up(stock):
    product = stock.product
    variant = stock.variant
    fields_to_scan = [
        (product.name or ""),
        (product.category or ""),
        (product.description or ""),
        (variant.name or "") if variant else "",
    ]
    if variant and isinstance(variant.attributes, dict):
        for key, value in variant.attributes.items():
            if isinstance(value, bool) and value and str(key).lower() in ("flag", "flagged", "thumbs_up", "thumbsup"):
                return True
            fields_to_scan.append(f"{key}:{value}")

    merged = " ".join(fields_to_scan).lower()
    markers = ("thumbs up", "thumbsup", "flagged", "[flag]", "#flag")
    return any(marker in merged for marker in markers)


def _build_event_key(*, stock, alert_type):
    if not stock.expiry_date:
        expiry = "none"
    elif hasattr(stock.expiry_date, "isoformat"):
        expiry = stock.expiry_date.isoformat()
    else:
        expiry = str(stock.expiry_date)
    return (
        f"{alert_type}:{stock.id}:{stock.location_id}:{stock.quantity}:"
        f"{expiry}:{stock.updated_at.isoformat()}"
    )


def _coerce_date(value):
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def get_users_for_stock(stock):
    location_id = stock.location_id
    if not location_id:
        return User.objects.none()
    return User.objects.filter(
        Q(is_active=True, role=ROLE_MANAGER, location_id=location_id)
        | Q(is_active=True, role=ROLE_ADMIN)
        | Q(is_active=True, is_superuser=True)
    ).distinct()


def create_alert(user, alert_type, message, *, location=None, reference_id=None, event_key=""):
    alert, created = Alert.objects.get_or_create(
        user=user,
        alert_type=alert_type,
        event_key=event_key or "",
        defaults={
            "message": message,
            "reference_id": reference_id,
            "location": location,
        },
    )
    if not created:
        return None
    return alert


def send_email(user, message):
    if not user.email:
        return False
    send_mail(
        subject="Inventory Alert",
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER),
        recipient_list=[user.email],
        fail_silently=True,
    )
    return True


def _send_whatsapp_request(phone_number, message):
    api_url = getattr(settings, "WHATSAPP_API_URL", "")
    if not api_url:
        return False

    payload = {
        "to": phone_number,
        "message": message,
    }
    from_number = getattr(settings, "WHATSAPP_FROM_NUMBER", "")
    if from_number:
        payload["from"] = from_number

    headers = {"Content-Type": "application/json"}
    token = getattr(settings, "WHATSAPP_API_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(
        url=api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        request.urlopen(req, timeout=_get_whatsapp_timeout())
    except error.URLError:
        logger.warning("WhatsApp send failed", extra={"phone_number": phone_number})
        return False
    return True


def send_whatsapp(user, message):
    if not user.phone_number:
        return False
    return _send_whatsapp_request(user.phone_number, message)


def _dispatch_to_user(*, user, alert_type, message, location, reference_id, event_key):
    alert = create_alert(
        user=user,
        alert_type=alert_type,
        message=message,
        location=location,
        reference_id=reference_id,
        event_key=event_key,
    )
    if not alert:
        return False
    send_email(user, message)
    send_whatsapp(user, message)
    return True


def _dispatch_stock_alert(stock, *, alert_type, message):
    event_key = _build_event_key(stock=stock, alert_type=alert_type)
    users = get_users_for_stock(stock)
    for user in users:
        _dispatch_to_user(
            user=user,
            alert_type=alert_type,
            message=message,
            location=stock.location,
            reference_id=stock.id,
            event_key=event_key,
        )


def notify_stock_state_change(stock, *, previous_quantity=None, previous_expiry_date=None, created=False):
    quantity_changed = created or previous_quantity is None or previous_quantity != stock.quantity
    expiry_changed = created or previous_expiry_date != stock.expiry_date

    if not quantity_changed and not expiry_changed:
        return

    item_name = _build_stock_item_name(stock)
    location_name = stock.location.name

    if quantity_changed:
        _dispatch_stock_alert(
            stock,
            alert_type="stock_update",
            message=f"Stock updated for {item_name} at {location_name}. Current quantity: {stock.quantity}.",
        )

    threshold = _get_low_stock_threshold()
    if 0 < stock.quantity <= threshold:
        _dispatch_stock_alert(
            stock,
            alert_type="low_stock",
            message=f"Low stock for {item_name} at {location_name}. Remaining quantity: {stock.quantity}.",
        )

    if stock.quantity == 0:
        _dispatch_stock_alert(
            stock,
            alert_type="zero_stock",
            message=f"Zero stock for {item_name} at {location_name}. Immediate replenishment required.",
        )

    expiry_days = _get_expiry_alert_days()
    expiry_date = _coerce_date(stock.expiry_date)
    if expiry_date and stock.quantity > 0:
        today = date.today()
        threshold_date = today + timedelta(days=expiry_days)
        if today <= expiry_date <= threshold_date:
            _dispatch_stock_alert(
                stock,
                alert_type="expiry",
                message=(
                    f"Expiry alert: {item_name} at {location_name} expires on "
                    f"{expiry_date.isoformat()}."
                ),
            )

    if _detect_flagged_or_thumbs_up(stock):
        _dispatch_stock_alert(
            stock,
            alert_type="flagged",
            message=f"Flagged item update detected for {item_name} at {location_name}.",
        )


def run_expiry_notifications():
    today = date.today()
    expiry_days = _get_expiry_alert_days()
    threshold_date = today + timedelta(days=expiry_days)
    stocks = Stock.objects.select_related("product", "variant", "location").filter(
        expiry_date__gte=today,
        expiry_date__lte=threshold_date,
        quantity__gt=0,
    )
    for stock in stocks:
        notify_stock_state_change(stock, previous_quantity=stock.quantity, previous_expiry_date=None, created=False)


def get_alerts_for_user(user):
    alerts = Alert.objects.filter(user=user)
    return [
        {
            "id": a.id,
            "type": a.alert_type,
            "message": a.message,
            "is_read": a.is_read,
            "created_at": a.created_at,
        }
        for a in alerts
    ]


def get_unread_count_for_user(user):
    return Alert.objects.filter(
        user=user,
        is_read=False
    ).count()


def mark_alert_read_for_user(user, alert_id):
    alert = Alert.objects.filter(id=alert_id, user=user).first()
    if not alert:
        raise Http404("Alert not found")
    alert.is_read = True
    alert.save()
