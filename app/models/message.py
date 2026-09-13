import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, DateTime, func

class MessageBase(SQLModel):
    eventId: str = Field(foreign_key="event.id", index=True)
    senderId: str = Field(foreign_key="user.id", index=True)
    text: str
    isFlagged: bool = Field(default=False)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now()))

class Message(MessageBase, table=True):
    __tablename__ = "Message"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    # Relationships
    event: "Event" = Relationship(back_populates="messages")
    sender: "User" = Relationship(back_populates="messages")
