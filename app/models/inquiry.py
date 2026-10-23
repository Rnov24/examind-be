from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.core.database import Base


class Inquiry(Base):
    """A consultation/sales inquiry submitted from the public landing page.

    Before this model existed the landing form only *pretended* to submit
    (local state + a WhatsApp deep link). Inquiries are now persisted so the
    superadmin can actually follow them up.
    """

    __tablename__ = "inquiries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(150), nullable=False)
    role = Column(String(150), nullable=True)
    school_name = Column(String(200), nullable=False)
    whatsapp = Column(String(30), nullable=False, index=True)
    package_interest = Column(String(200), nullable=True)
    student_count_range = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    # new | contacted | closed
    status = Column(String(20), nullable=False, default="new", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
