from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class MessageCreate(BaseModel):
    text: str

class MessageResponse(BaseModel):
    id: str
    senderId: str
    senderName: str
    text: str
    time: str
    isMe: bool
    timestamp: int

class ChatEventResponse(BaseModel):
    id: str
    title: str
    updatedAt: datetime
    
class ChatEventsListResponse(BaseModel):
    events: List[ChatEventResponse]
