import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, String, Float, DateTime, func
from sqlalchemy.dialects.postgresql import ARRAY
import sqlalchemy as sa

class UserBase(SQLModel):
    studentEmail: str = Field(unique=True, index=True)
    passwordHash: str
    displayName: Optional[str] = None
    isVerified: bool = Field(default=False)
    age: Optional[int] = None
    university: Optional[str] = None
    yearOfStudy: Optional[int] = None
    isFirstTimeUni: Optional[bool] = None
    isInternationalStudent: Optional[bool] = Field(default=False)
    isFirstLogin: bool = Field(default=True)
    bio: Optional[str] = None
    introvertExtrovertScore: Optional[int] = None
    socialEnergyLevel: Optional[str] = None

    interests: List[str] = Field(default=[], sa_column=Column(ARRAY(String)))
    languages: List[str] = Field(default=[], sa_column=Column(ARRAY(String)))
    lookingForTags: List[str] = Field(default=[], sa_column=Column(ARRAY(String)))
    extractedAiTags: List[str] = Field(default=[], sa_column=Column(ARRAY(String)))
    cachedVectorEmbedding: List[float] = Field(default=[], sa_column=Column(ARRAY(Float)))

    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()))
    lastVerifiedAt: Optional[datetime] = None

class User(UserBase, table=True):
    __tablename__ = "User"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    # Relationships
    hostedEvents: List["Event"] = Relationship(back_populates="host")
    participatedEvents: List["EventParticipant"] = Relationship(back_populates="user")
    messages: List["Message"] = Relationship(back_populates="sender")
    eventRationales: List["EventRationale"] = Relationship(back_populates="user")
