from sqlalchemy import Column, DateTime, Integer, Text
from sqlalchemy.sql import func

from db import Base


class EmailRecord(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    gmail_message_id = Column(Text, unique=True, nullable=False, index=True)
    thread_id = Column(Text, nullable=True)
    subject = Column(Text, nullable=False, default="")
    sender = Column(Text, nullable=True)
    recipients = Column(Text, nullable=True)
    sent_at = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    attachment_names = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
