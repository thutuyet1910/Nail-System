from datetime import datetime

from sqlalchemy.orm import Session

import models
from timeutils import utc_now_naive
from phone_normalization import normalize_us_phone


NOTIFICATION_TYPES = {
    "phone_booking", "phone_reschedule", "phone_cancellation", "callback_request",
    "ambiguous_appointment", "ai_unable_to_answer", "failed_call", "system_issue",
}
SEVERITIES = {"info", "warning", "urgent"}
CALLBACK_CATEGORIES = {"general", "booking", "reschedule", "cancellation", "complaint", "other"}
_SECRET_FRAGMENTS = ("secret", "token", "password", "authorization", "api_key")


class NotificationRuleError(ValueError):
    pass


def _safe_metadata(metadata: dict | None) -> dict | None:
    if not metadata:
        return None
    if any(any(fragment in str(key).lower() for fragment in _SECRET_FRAGMENTS) for key in metadata):
        raise NotificationRuleError("Secret-bearing notification metadata keys are not allowed")
    return metadata


def create_notification(
    db: Session, *, notification_type: str, severity: str, title: str, message: str,
    source_type: str, source_id: str | None = None, event_key: str | None = None,
    appointment_id: int | None = None, external_customer_id: int | None = None,
    metadata: dict | None = None, commit: bool = True,
) -> models.OwnerNotification:
    if notification_type not in NOTIFICATION_TYPES:
        raise NotificationRuleError("Unsupported notification type")
    if severity not in SEVERITIES:
        raise NotificationRuleError("Unsupported notification severity")
    if event_key:
        existing = db.query(models.OwnerNotification).filter(models.OwnerNotification.event_key == event_key).first()
        if existing:
            return existing
    item = models.OwnerNotification(
        notification_type=notification_type, severity=severity, title=title.strip(),
        message=message.strip(), source_type=source_type, source_id=source_id,
        event_key=event_key, appointment_id=appointment_id,
        external_customer_id=external_customer_id, metadata_json=_safe_metadata(metadata),
        created_at=utc_now_naive(),
    )
    db.add(item)
    if commit:
        db.commit()
        db.refresh(item)
    else:
        db.flush()
    return item


def list_notifications(db: Session, *, unread_only=False, severity=None, notification_type=None, start=None, end=None, limit=100):
    query = db.query(models.OwnerNotification)
    if unread_only:
        query = query.filter(models.OwnerNotification.read_at.is_(None))
    if severity:
        query = query.filter(models.OwnerNotification.severity == severity)
    if notification_type:
        query = query.filter(models.OwnerNotification.notification_type == notification_type)
    if start:
        query = query.filter(models.OwnerNotification.created_at >= start)
    if end:
        query = query.filter(models.OwnerNotification.created_at <= end)
    return query.order_by(models.OwnerNotification.created_at.desc(), models.OwnerNotification.id.desc()).limit(min(limit, 200)).all()


def unread_count(db: Session) -> int:
    return db.query(models.OwnerNotification).filter(models.OwnerNotification.read_at.is_(None)).count()


def mark_read(db: Session, notification_id: int):
    item = db.get(models.OwnerNotification, notification_id)
    if not item:
        return None
    if not item.read_at:
        item.read_at = utc_now_naive()
        db.commit()
        db.refresh(item)
    return item


def mark_all_read(db: Session) -> int:
    now = utc_now_naive()
    count = db.query(models.OwnerNotification).filter(models.OwnerNotification.read_at.is_(None)).update({"read_at": now}, synchronize_session=False)
    db.commit()
    return count


def request_owner_callback(
    db: Session, *, caller_phone: str, category: str, urgency: str = "normal",
    summary: str, operation_key: str, external_customer_id: int | None = None,
    appointment_id: int | None = None, phone_trusted: bool = True,
) -> models.OwnerNotification:
    """phone_trusted=False marks a number the caller merely SAID (never provider caller ID)."""
    if category not in CALLBACK_CATEGORIES:
        raise NotificationRuleError("Unsupported callback category")
    caller_phone = normalize_us_phone(caller_phone).e164
    severity = "urgent" if urgency == "urgent" else "warning"
    return create_notification(
        db, notification_type="callback_request", severity=severity,
        title="Customer callback requested", message=summary,
        source_type="callback_request", source_id=caller_phone,
        event_key=f"callback:{operation_key}", appointment_id=appointment_id,
        external_customer_id=external_customer_id,
        metadata={"caller_phone": caller_phone, "category": category, "urgency": urgency, "phone_source": "caller_id" if phone_trusted else "spoken_by_caller"},
    )
