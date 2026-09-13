import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Float, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY

class EventParticipant(SQLModel, table=True):
    __tablename__ = "EventParticipant"
    __table_args__ = (UniqueConstraint('eventId', 'userId', name='_event_user_uc'),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    eventId: str = Field(foreign_key="event.id", index=True)
    userId: str = Field(foreign_key="user.id", index=True)
    joinedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now()))

    # Relationships
    event: "Event" = Relationship(back_populates="participants")
    user: "User" = Relationship(back_populates="participatedEvents")

class EventBase(SQLModel):
    title: str
    category: str
    description: str
    startTime: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    endTime: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    location: str
    maxParticipants: int
    goalCategory: Optional[str] = None
    targetEnergyNumeric: Optional[int] = None
    cachedVectorEmbedding: List[float] = Field(default=[], sa_column=Column(ARRAY(Float)))
    status: str = Field(default="ACTIVE")
    
    hostId: str = Field(foreign_key="user.id")

    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()))

class Event(EventBase, table=True):
    __tablename__ = "Event"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    
    # Relationships
    host: "User" = Relationship(back_populates="hostedEvents")
    participants: List[EventParticipant] = Relationship(back_populates="event")
    messages: List["Message"] = Relationship(back_populates="event")
    eventRationales: List["EventRationale"] = Relationship(back_populates="event")
