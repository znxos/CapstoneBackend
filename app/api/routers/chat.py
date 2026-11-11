from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload
from datetime import datetime
import pusher

from app.api.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.event import Event, EventParticipant
from app.models.message import Message
from app.schemas.chat import MessageCreate, MessageResponse, ChatEventsListResponse
from app.core.config import settings
# from app.services.moderation import execute_moderation

router = APIRouter(prefix="/api/chat", tags=["chat"])

pusher_client = None
if settings.NEXT_PUBLIC_PUSHER_APP_ID:
    pusher_client = pusher.Pusher(
        app_id=settings.NEXT_PUBLIC_PUSHER_APP_ID,
        key=settings.NEXT_PUBLIC_PUSHER_KEY,
        secret=settings.PUSHER_SECRET,
        cluster=settings.NEXT_PUBLIC_PUSHER_CLUSTER,
        ssl=True,
        encryption_master_key_base64=settings.PUSHER_ENCRYPTION_KEY
    )

@router.get("/events", response_model=ChatEventsListResponse)
async def get_chat_events(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Get hosted and participated events
    user = await db.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    hosted = await db.execute(select(Event).where(Event.hostId == user.id))
    participated = await db.execute(
        select(Event).join(EventParticipant).where(EventParticipant.userId == user.id)
    )
    
    all_events = {e.id: e for e in hosted.scalars().all()}
    for e in participated.scalars().all():
        all_events[e.id] = e
        
    events_list = list(all_events.values())
    events_list.sort(key=lambda x: x.updatedAt, reverse=True)
    
    return {"events": events_list}

@router.get("/events/{event_id}/messages")
async def get_messages(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Check membership: host or participant
    is_host = await db.execute(select(Event).where(Event.id == event_id, Event.hostId == current_user.id))
    is_participant = await db.execute(
        select(EventParticipant).where(EventParticipant.eventId == event_id, EventParticipant.userId == current_user.id)
    )
    
    if not is_host.scalars().first() and not is_participant.scalars().first():
        raise HTTPException(status_code=403, detail="You are not a participant of this event.")

    result = await db.execute(
        select(Message)
        .options(selectinload(Message.sender))
        .where(Message.eventId == event_id)
        .order_by(Message.timestamp)
    )
    messages = result.scalars().all()
    
    formatted = []
    for m in messages:
        formatted.append({
            "id": m.id,
            "senderId": m.senderId,
            "senderName": m.sender.displayName or "Unknown",
            "text": "This message has been removed for violating our community guidelines." if m.isFlagged else m.text,
            "time": f"{m.timestamp.hour:02d}:{m.timestamp.minute:02d}",
            "isMe": m.senderId == current_user.id,
            "timestamp": int(m.timestamp.timestamp() * 1000)
        })
        
    return {"messages": formatted, "currentUserId": current_user.id}

@router.post("/events/{event_id}/messages")
async def send_message(
    event_id: str,
    msg: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not msg.text or not msg.text.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
        
    # Check membership
    is_host = await db.execute(select(Event).where(Event.id == event_id, Event.hostId == current_user.id))
    is_participant = await db.execute(
        select(EventParticipant).where(EventParticipant.eventId == event_id, EventParticipant.userId == current_user.id)
    )
    
    if not is_host.scalars().first() and not is_participant.scalars().first():
        raise HTTPException(status_code=403, detail="You are not a participant of this event.")
        
    # Anti-spam
    last_msg_res = await db.execute(
        select(Message)
        .where(Message.eventId == event_id, Message.senderId == current_user.id)
        .order_by(Message.timestamp.desc())
        .limit(1)
    )
    last_message = last_msg_res.scalars().first()
    
    if last_message:
        time_diff = (datetime.utcnow().timestamp() - last_message.timestamp.timestamp()) * 1000
        if time_diff < 1000:
            raise HTTPException(status_code=429, detail="You are sending messages too quickly.")
        if last_message.text == msg.text and time_diff < 10000:
            raise HTTPException(status_code=429, detail="Duplicate message detected.")
            
    # Save message
    message = Message(
        eventId=event_id,
        senderId=current_user.id,
        text=msg.text,
        isFlagged=False
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    payload = {
        "id": message.id,
        "senderId": current_user.id,
        "senderName": current_user.displayName or "Unknown",
        "text": message.text,
        "time": f"{message.timestamp.hour:02d}:{message.timestamp.minute:02d}",
        "timestamp": int(message.timestamp.timestamp() * 1000)
    }
    
    # Broadcast
    if pusher_client:
        try:
            pusher_client.trigger(f"private-encrypted-{event_id}", "incoming-message", payload)
        except Exception as e:
            print("Pusher error:", e)
            
    # Moderation (async in background)
    from app.services.moderation import moderation_queue
    moderation_queue.put_nowait({
        "messageId": message.id,
        "eventId": event_id,
        "text": msg.text
    })
    
    return {"success": True, "message": payload}

from fastapi import Request, Form
@router.post("/pusher/auth")
async def pusher_auth(
    request: Request,
    socket_id: str = Form(...),
    channel_name: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not pusher_client:
        raise HTTPException(status_code=500, detail="Pusher not configured")
        
    if not current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Extract event_id from channel_name (e.g. "private-encrypted-<event_id>" or "private-<event_id>")
    event_id = channel_name
    if channel_name.startswith("private-encrypted-"):
        event_id = channel_name[len("private-encrypted-"):]
    elif channel_name.startswith("private-"):
        event_id = channel_name[len("private-"):]
        
    # Verify the user is either the host or a participant of the event
    is_host = await db.execute(select(Event).where(Event.id == event_id, Event.hostId == current_user.id))
    is_participant = await db.execute(
        select(EventParticipant).where(EventParticipant.eventId == event_id, EventParticipant.userId == current_user.id)
    )
    if not is_host.scalars().first() and not is_participant.scalars().first():
        raise HTTPException(status_code=403, detail="You are not authorized to subscribe to this channel.")
        
    auth = pusher_client.authenticate(
        channel=channel_name,
        socket_id=socket_id
    )
    return auth
