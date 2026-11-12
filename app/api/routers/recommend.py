from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload
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
    generate_more: bool = Query(False),
    pool_size: int | None = Query(None, ge=1),
    full_pool: bool = Query(False),
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
            category=category,
            generate_more=generate_more,
            pool_size=pool_size,
            full_pool=full_pool
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
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
    stmt = (
        select(Event)
        .options(selectinload(Event.host))
        .where(Event.id == event_id)
        .with_for_update()
    )
    result = await db.execute(stmt)
    event = result.scalars().first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
        
    # Check if event has ended or is inactive
    now = datetime.now(timezone.utc)
    event_end = event.endTime if (event.endTime and event.endTime.tzinfo) else (event.endTime.replace(tzinfo=timezone.utc) if event.endTime else None)
    if event_end and event_end <= now:
        raise HTTPException(status_code=400, detail="Cannot join an event that has already ended")
    if event.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="Cannot join an inactive event")

    # check if already joined (idempotent)
    existing = await db.execute(select(EventParticipant).where(EventParticipant.eventId == event_id, EventParticipant.userId == current_user.id))
    if existing.scalars().first():
        return {"success": True}

    if event.host:
        # Enforce Campus Isolation Policy
        if current_user.university:
            host_uni = (event.host.university or "").strip().upper()
            user_uni = current_user.university.strip().upper()
            if host_uni and user_uni and host_uni != user_uni:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Campus isolation policy: You can only join events hosted within your university."
                )

        # Enforce 1st-Year Ring-Fencing Safety Restriction
        user_is_first_year = bool(current_user.age and current_user.age <= 19 and current_user.yearOfStudy == 1)
        host_is_first_year = bool(
            event.host.age 
            and event.host.age <= 19 
            and event.host.yearOfStudy == 1
        )
        if user_is_first_year != host_is_first_year:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Safety policy: First-year student ring-fencing restriction applies."
            )

    # check capacity
    result = await db.execute(select(EventParticipant).where(EventParticipant.eventId == event_id))
    participant_count = len(result.scalars().all())
    
    if participant_count >= event.maxParticipants:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Event Capacity Reached")
        
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
