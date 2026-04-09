from sqlalchemy import Boolean, Column, DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.sql import func

from db import Base


class EmailRecord(Base):
    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("account_id", "gmail_message_id", name="uq_emails_account_message"),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Text, nullable=False, default="local_default", index=True)
    gmail_message_id = Column(Text, nullable=False, index=True)
    thread_id = Column(Text, nullable=True)
    subject = Column(Text, nullable=False, default="")
    sender = Column(Text, nullable=True)
    recipients = Column(Text, nullable=True)
    sent_at = Column(Text, nullable=True)
    gmail_category = Column(Text, nullable=True, index=True)
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


class SyncMeta(Base):
    __tablename__ = "sync_meta"
    __table_args__ = (
        UniqueConstraint("account_id", "key", name="uq_sync_meta_account_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Text, nullable=False, default="local_default", index=True)
    key = Column(Text, nullable=False)
    value = Column(Text, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Text, unique=True, nullable=False, index=True)
    email_address = Column(Text, nullable=True, index=True)
    display_name = Column(Text, nullable=True)
    token_path = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
