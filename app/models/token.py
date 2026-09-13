import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime, func

class VerificationToken(SQLModel, table=True):
    __tablename__ = "VerificationToken"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(index=True)
    token: str = Field(unique=True, index=True)
    expiresAt: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now()))

class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "PasswordResetToken"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(index=True)
    token: str = Field(unique=True, index=True)
    expiresAt: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now()))
