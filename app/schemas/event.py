from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class EventCreate(BaseModel):
    title: str
    category: str
    description: str
    startTime: str
    endTime: str
    location: str
    maxParticipants: int

class EventResponse(BaseModel):
    id: str
    title: str
    category: str
    description: str
    datetime: str
    location: str
    capacity: int
    joinedCount: int
    similarity: Optional[int] = None
    rationale: Optional[str] = None
    participants: List[str] = []
    isJoined: bool = False
    isHost: bool = False

class EventListResponse(BaseModel):
    events: List[EventResponse]
    totalCount: int
