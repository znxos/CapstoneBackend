import pytest
from httpx import AsyncClient
from sqlmodel import select
from app.models.user import User
from app.models.event import Event, EventParticipant
from tests.conftest import TestingSessionLocal
from datetime import datetime, timezone, timedelta
import uuid

@pytest.mark.asyncio
async def test_tc004_event_capacity_limit(async_client: AsyncClient, setup_db):
    """
    TC-004: Event Capacity Limits
    Attempt to join a recommended event that already has its max participants.
    Expected: Rejected by the backend (HTTP 409 Conflict).
    """
    # Create test data
    async with TestingSessionLocal() as session:
        # Create an event with max_participants = 3 for testing
        event = Event(
            title="Test Event",
            category="Tech",
            description="A test event",
            startTime=datetime.now(timezone.utc),
            endTime=datetime.now(timezone.utc) + timedelta(hours=2),
            location="Room A",
            maxParticipants=3,
            hostId=str(uuid.uuid4()),
            status="ACTIVE"
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        
        # Add 3 participants to hit the cap
        for i in range(3):
            p = EventParticipant(eventId=event.id, userId=str(uuid.uuid4()))
            session.add(p)
        
        # Create the user trying to join
        joining_user = User(
            studentEmail="joiner@cput.ac.za",
            passwordHash="hashed",
            isVerified=True
        )
        session.add(joining_user)
        await session.commit()
        await session.refresh(joining_user)

    # We need to mock authentication to act as joining_user
    # We can use the create_access_token from security
    from app.core.security import create_access_token
    access_token = create_access_token(
        subject=str(joining_user.id),
        expires_delta=timedelta(minutes=15)
    )
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Try to join the event
    response = await async_client.post(
        f"/api/events/{event.id}/join",
        headers=headers
    )
    
    assert response.status_code == 409
    assert response.json()["detail"] == "Event Capacity Reached"
