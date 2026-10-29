import pytest
from httpx import AsyncClient
from sqlmodel import select
from app.models.user import User
from app.models.event import Event
from tests.conftest import TestingSessionLocal
from datetime import datetime, timezone
import uuid
from app.core.security import create_access_token
from datetime import timedelta

@pytest.mark.asyncio
async def test_tc003_first_year_ring_fencing(async_client: AsyncClient, setup_db):
    """
    TC-003: First-Year Ring-Fencing
    A 1st-year student (Age 18-19, Year 1) attempts to view or match with an event hosted by a 3rd-year student.
    Expected: The event is entirely hidden from the 1st-year student's feed.
    """
    async with TestingSessionLocal() as session:
        # Create a 3rd-year host
        host = User(
            studentEmail="host@cput.ac.za", 
            passwordHash="hashed", 
            isVerified=True,
            age=21,
            yearOfStudy=3,
            university="CPUT"
        )
        session.add(host)
        await session.commit()
        await session.refresh(host)
        
        # Host creates an event
        event = Event(
            title="Senior Tech Talk",
            category="Tech",
            description="Advanced topics",
            startTime=datetime.now(timezone.utc),
            endTime=datetime.now(timezone.utc),
            location="Room B",
            maxParticipants=10,
            hostId=host.id,
            status="ACTIVE"
        )
        session.add(event)
        
        # Create a 1st-year user
        first_year_user = User(
            studentEmail="freshman@cput.ac.za", 
            passwordHash="hashed", 
            isVerified=True,
            age=18,
            yearOfStudy=1,
            university="CPUT"
        )
        session.add(first_year_user)
        await session.commit()
        await session.refresh(first_year_user)

    # Authenticate as first year
    access_token = create_access_token(
        subject=str(first_year_user.id),
        expires_delta=timedelta(minutes=15)
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Request recommended events
    response = await async_client.get(
        "/api/events?tab=recommended",
        headers=headers
    )
    
    assert response.status_code == 200
    events = response.json().get("events", [])
    
    # Ensure the senior event is NOT in the list
    event_ids = [e["id"] for e in events]
    assert event.id not in event_ids

@pytest.mark.skip(reason="Cron job for unassigned rotation is not yet implemented in backend")
@pytest.mark.asyncio
async def test_tc010_unassigned_rotation_job(async_client: AsyncClient, setup_db):
    """
    TC-010: Unassigned Rotation Job
    Run the 3-hour cron job on an event where an invited user has not joined the room.
    Expected: The unresponsive user is unassigned, and the Recommender pulls the next candidate.
    """
    pass
