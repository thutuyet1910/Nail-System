from datetime import datetime
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship

from database import Base


class Technician(Base):
    __tablename__ = "technicians"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, unique=True, nullable=True, index=True)
    full_name = Column(String, nullable=False, index=True)
    phone = Column(String, nullable=True)
    skills = Column(String, nullable=True)
    specialties = Column(String, nullable=True)
    start_date = Column(Date, nullable=True)

    status = Column(String, nullable=False, default="off")
    availability = Column(String, nullable=False, default="off today")
    work_schedule = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    profile_photo = Column(String, nullable=True)

    appointments = relationship(
        "Appointment",
        foreign_keys="Appointment.technician_id",
        back_populates="technician",
        cascade="all, delete"
    )

    preferred_appointments = relationship(
        "Appointment",
        foreign_keys="Appointment.preferred_technician_id",
        back_populates="preferred_technician"
    )

    turns = relationship(
        "Turn",
        foreign_keys="Turn.technician_id",
        back_populates="technician",
        cascade="all, delete"
    )

    preferred_turns = relationship(
        "Turn",
        foreign_keys="Turn.preferred_technician_id",
        back_populates="preferred_technician"
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    appointment_code = Column(String, unique=True, nullable=False, index=True)

    customer_name = Column(String, nullable=False, index=True)
    customer_phone = Column(String, nullable=False, index=True)

    service_name = Column(String, nullable=False)
    service_category = Column(String, nullable=False)

    appointment_time = Column(DateTime, nullable=False, index=True)

    customer_type = Column(String, nullable=False, default="new")
    note = Column(Text, nullable=True)
    special_requests = Column(Text, nullable=True)
    allergies = Column(Text, nullable=True)

    people_count = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)
    preferred_technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)

    technician = relationship(
        "Technician",
        foreign_keys=[technician_id],
        back_populates="appointments"
    )

    preferred_technician = relationship(
        "Technician",
        foreign_keys=[preferred_technician_id],
        back_populates="preferred_appointments"
    )


class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True, index=True)
    turn_number = Column(Integer, nullable=False)

    discount_type = Column(String, nullable=True)
    discount_value = Column(Numeric(10, 2), nullable=True, default=0)
    discount_label = Column(String, nullable=True)

    customer_name = Column(String, nullable=False)
    customer_phone = Column(String, nullable=True)
    service_name = Column(String, nullable=False)

    status = Column(String, nullable=False, default="waiting")
    source = Column(String, nullable=False, default="checkin")
    assigned_by = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=False)
    preferred_technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)

    technician = relationship(
        "Technician",
        foreign_keys=[technician_id],
        back_populates="turns"
    )

    preferred_technician = relationship(
        "Technician",
        foreign_keys=[preferred_technician_id],
        back_populates="preferred_turns"
    )

class Checkout(Base):
    __tablename__ = "checkouts"

    id = Column(Integer, primary_key=True, index=True)

    customer_name = Column(String, nullable=False, index=True)
    customer_phone = Column(String, nullable=True, index=True)

    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)
    turn_id = Column(Integer, ForeignKey("turns.id"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)

    payment_method = Column(String, nullable=False, default="cash")
    service_name = Column(String, nullable=False)

    subtotal = Column(Numeric(10, 2), nullable=False, default=0)
    discount_type = Column(String, nullable=False, default="none")
    discount_value = Column(Numeric(10, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0)
    discount_paid_by = Column(String, nullable=False, default="owner")

    tip_amount = Column(Numeric(10, 2), nullable=False, default=0)
    net_service = Column(Numeric(10, 2), nullable=False, default=0)
    technician_share = Column(Numeric(10, 2), nullable=False, default=0)
    salon_share = Column(Numeric(10, 2), nullable=False, default=0)
    salon_actual_revenue = Column(Numeric(10, 2), nullable=False, default=0)
    technician_total = Column(Numeric(10, 2), nullable=False, default=0)
    customer_pays = Column(Numeric(10, 2), nullable=False, default=0)

    note = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    supplier = Column(String, nullable=True)
    quantity = Column(Integer, nullable=False, default=0)
    unit_price = Column(Numeric(10, 2), nullable=False, default=0)
    purchase_date = Column(Date, nullable=True)
    low_stock_level = Column(Integer, nullable=False, default=3)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)