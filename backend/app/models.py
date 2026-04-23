from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=False)

    referral_code = Column(String, unique=True, nullable=True)
    referral_count = Column(Integer, default=0, nullable=False)
    referral_discount_percent = Column(Integer, default=10)
    referral_discount_pending = Column(Boolean, default=False, nullable=False)

    birthday_discount_amount = Column(Integer, default=10)
    birthday_discount_used_month = Column(String, nullable=True)

    visit_count_cycle = Column(Integer, default=0)
    visit_discount_pending = Column(Boolean, default=False, nullable=False)

    used_referral_code = Column(String, nullable=True)
    used_referral_from_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

    birthday_reminder_sent = Column(Boolean, default=False)
    birthday_reminder_sent_date = Column(Date, nullable=True)

    visits = relationship("Visit", back_populates="customer", cascade="all, delete-orphan")
    referral_usages_as_owner = relationship(
        "ReferralUsage",
        foreign_keys="ReferralUsage.code_owner_customer_id",
        back_populates="code_owner",
        cascade="all, delete-orphan",
    )
    referral_usages_as_user = relationship(
        "ReferralUsage",
        foreign_keys="ReferralUsage.used_by_customer_id",
        back_populates="used_by_customer",
        cascade="all, delete-orphan",
    )


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    visit_date = Column(Date, nullable=False)
    checked_in_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="visits")
    visit_services = relationship("VisitService", back_populates="visit", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    visit_services = relationship("VisitService", back_populates="service", cascade="all, delete-orphan")


class VisitService(Base):
    __tablename__ = "visit_services"

    id = Column(Integer, primary_key=True, index=True)
    visit_id = Column(Integer, ForeignKey("visits.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)

    visit = relationship("Visit", back_populates="visit_services")
    service = relationship("Service", back_populates="visit_services")


class ReferralUsage(Base):
    __tablename__ = "referral_usages"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=False)
    code_owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    used_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    used_on = Column(Date, nullable=False)

    code_owner = relationship(
        "Customer",
        foreign_keys=[code_owner_customer_id],
        back_populates="referral_usages_as_owner",
    )
    used_by_customer = relationship(
        "Customer",
        foreign_keys=[used_by_customer_id],
        back_populates="referral_usages_as_user",
    )