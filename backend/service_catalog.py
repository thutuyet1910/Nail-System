"""Owner-only management of the booking service catalog (the database is the source of truth).

Services are never deleted: appointments reference them, so retiring a service means
is_active=False. Appointments keep their own name/duration/price/buffer snapshots, so editing
a service never rewrites history.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import models


class ServiceCatalogError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


_NOT_NULLABLE = ("name", "duration_minutes", "buffer_before_minutes", "buffer_after_minutes", "is_active")


def serialize(service: models.BookingService) -> dict:
    return {
        "id": service.id, "name": service.name, "category": service.category,
        "description": service.description, "duration_minutes": service.duration_minutes,
        "price": float(service.price) if service.price is not None else None,
        "buffer_before_minutes": service.buffer_before_minutes,
        "buffer_after_minutes": service.buffer_after_minutes,
        "is_active": service.is_active,
        "eligible_technician_ids": sorted(item.technician_id for item in service.technician_eligibilities),
    }


def list_services(db: Session) -> list[dict]:
    rows = (
        db.query(models.BookingService)
        .options(joinedload(models.BookingService.technician_eligibilities))
        .order_by(models.BookingService.category, models.BookingService.name)
        .all()
    )
    return [serialize(row) for row in rows]


def list_internal(db: Session, include_inactive: bool = False) -> list[models.BookingService]:
    query = db.query(models.BookingService)
    if not include_inactive:
        query = query.filter(models.BookingService.is_active.is_(True))
    return query.order_by(models.BookingService.id).all()


def _get(db: Session, service_id: int) -> models.BookingService:
    service = db.get(models.BookingService, service_id)
    if not service:
        raise ServiceCatalogError("Service not found", 404)
    return service


def _ensure_unique_name(db: Session, name: str, exclude_id: int | None = None) -> None:
    query = db.query(models.BookingService.id).filter(func.lower(models.BookingService.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(models.BookingService.id != exclude_id)
    if query.first():
        raise ServiceCatalogError("A service with this name already exists", 409)


def create_service(db: Session, payload) -> dict:
    _ensure_unique_name(db, payload.name)
    service = models.BookingService(
        name=payload.name, category=payload.category, description=payload.description,
        duration_minutes=payload.duration_minutes, price=payload.price,
        buffer_before_minutes=payload.buffer_before_minutes,
        buffer_after_minutes=payload.buffer_after_minutes, is_active=payload.is_active,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return serialize(service)


def update_service(db: Session, service_id: int, payload) -> dict:
    service = _get(db, service_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in _NOT_NULLABLE:
        if field in changes and changes[field] is None:
            raise ServiceCatalogError(f"{field} cannot be empty")
    if "name" in changes:
        _ensure_unique_name(db, changes["name"], exclude_id=service.id)
    for field, value in changes.items():  # price/category/description may be set to NULL
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return serialize(service)


def set_service_technicians(db: Session, service_id: int, technician_ids: list[int]) -> dict:
    service = _get(db, service_id)
    wanted = set(technician_ids)
    found = {row[0] for row in db.query(models.Technician.id).filter(models.Technician.id.in_(wanted)).all()} if wanted else set()
    if found != wanted:
        raise ServiceCatalogError("One or more technicians do not exist")
    current = {item.technician_id: item for item in service.technician_eligibilities}
    for technician_id, item in current.items():
        if technician_id not in wanted:
            service.technician_eligibilities.remove(item)
    for technician_id in sorted(wanted - set(current)):
        service.technician_eligibilities.append(models.TechnicianService(technician_id=technician_id))
    db.commit()
    db.refresh(service)
    return serialize(service)
