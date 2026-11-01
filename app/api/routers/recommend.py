from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from datetime import datetime, timezone, timedelta

from app.api.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.event import Event, EventParticipant
from app.schemas.event import EventCreate, EventListResponse
from app.services.recommender import get_recommended_events
from app.services.llm_service import generate_event_embedding

router = APIRouter(prefix="/api/events", tags=["events"])

@router.get("", response_model=EventListResponse)
async def get_events(
    page: int = Query(1, ge=1),
    limit: int = Query(6, ge=1, le=50),
    tab: str = Query("recommended", pattern="^(recommended|my-events|created-events)$"),
    category: str = Query("All"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        return await get_recommended_events(
            db=db,
            user=current_user,
            page=page,
            limit=limit,
            tab=tab,
            category=category
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Failed to get events")

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(
    event_data: EventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not (3 <= event_data.maxParticipants <= 10):
        raise HTTPException(status_code=400, detail="Event capacity must be between 3 and 10 participants.")
        
    vector = await generate_event_embedding({
        "title": event_data.title,
        "category": event_data.category,
        "description": event_data.description
    })
    
    try:
        start = datetime.fromisoformat(event_data.startTime.replace("Z", "+00:00"))
        end = datetime.fromisoformat(event_data.endTime.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date or time format.")

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if end <= start:
        raise HTTPException(status_code=400, detail="Event end date and time must be after the start date and time.")
    if end <= now:
        raise HTTPException(status_code=400, detail="Event end date and time cannot be in the past.")
    if start < now - timedelta(minutes=15):
        raise HTTPException(status_code=400, detail="Event start date and time cannot be in the past.")
    
    new_event = Event(
        title=event_data.title,
        category=event_data.category,
        description=event_data.description,
        startTime=start,
        endTime=end,
        location=event_data.location,
        maxParticipants=event_data.maxParticipants,
        hostId=current_user.id,
        cachedVectorEmbedding=vector,
        status="ACTIVE"
    )
    db.add(new_event)
    await db.commit()
    await db.refresh(new_event)
    
    # Host joins automatically
    participant = EventParticipant(eventId=new_event.id, userId=current_user.id)
    db.add(participant)
    await db.commit()
    
    return {"success": True, "eventId": new_event.id}

@router.post("/{event_id}/join")
async def join_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # check capacity
    result = await db.execute(select(EventParticipant).where(EventParticipant.eventId == event_id))
    participant_count = len(result.scalars().all())
    
    if participant_count >= event.maxParticipants:
        raise HTTPException(status_code=409, detail="Event Capacity Reached")
        
    # Check if event has ended
    now = datetime.now(timezone.utc)
    event_end = event.endTime if (event.endTime and event.endTime.tzinfo) else (event.endTime.replace(tzinfo=timezone.utc) if event.endTime else None)
    if event_end and event_end <= now:
        raise HTTPException(status_code=400, detail="Cannot join an event that has already ended")
        
    # check if already joined
    existing = await db.execute(select(EventParticipant).where(EventParticipant.eventId == event_id, EventParticipant.userId == current_user.id))
    if existing.scalars().first():
        return {"success": True} # Idempotent
        
    participant = EventParticipant(eventId=event_id, userId=current_user.id)
    db.add(participant)
    await db.commit()
    
    return {"success": True}

@router.post("/{event_id}/leave")
async def leave_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(EventParticipant).where(EventParticipant.eventId == event_id, EventParticipant.userId == current_user.id))
    participant = result.scalars().first()
    
    if participant:
        await db.delete(participant)
        await db.commit()
        
    return {"success": True}
