import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, DateTime, func, UniqueConstraint

class EventRationaleBase(SQLModel):
    eventId: str = Field(foreign_key="Event.id", index=True)
    userId: str = Field(foreign_key="User.id", index=True)
    rationale: str
    userProfileHash: str
    
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()))

class EventRationale(EventRationaleBase, table=True):
    __tablename__ = "EventRationale"
    __table_args__ = (UniqueConstraint('eventId', 'userId', name='_rationale_event_user_uc'),)
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    # Relationships
    event: "Event" = Relationship(back_populates="eventRationales")
    user: "User" = Relationship(back_populates="eventRationales")
