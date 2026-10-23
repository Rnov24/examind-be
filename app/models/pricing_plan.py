from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from app.core.database import Base


class PricingPlan(Base):
    __tablename__ = "pricing_plans"

    id = Column(String(50), primary_key=True)  # 'starter', 'pro', 'enterprise'
    name = Column(String(100), nullable=False)
    price_monthly = Column(Integer, nullable=False, default=0)
    price_annually = Column(Integer, nullable=False, default=0)
    max_students = Column(Integer, nullable=False, default=0)
    max_teachers = Column(Integer, nullable=False, default=0)
    max_storage_gb = Column(Integer, nullable=False, default=0)
    ai_credits_monthly = Column(Integer, nullable=False, default=0)
    proctoring_type = Column(String(30), nullable=False, default="single_camera")  # single_camera | dual_camera
    description = Column(Text, nullable=True)
    features = Column(JSON, nullable=True)  # list[str]
    is_popular = Column(Boolean, default=False, nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
