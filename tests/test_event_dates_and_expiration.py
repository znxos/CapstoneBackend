import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
import uuid
from app.models.user import User
from app.models.event import Event, EventParticipant
from app.core.security import create_access_token
from tests.conftest import TestingSessionLocal

@pytest.mark.asyncio
async def test_create_event_validation_dates(async_client: AsyncClient, setup_db):
    """
    Test event creation validation:
    1. end time <= start time -> rejected (400)
    2. end time in the past -> rejected (400)
    3. start time in the past -> rejected (400)
    """
    async with TestingSessionLocal() as session:
        user = User(
            studentEmail="organizer@cput.ac.za",
            passwordHash="hashed",
            isVerified=True,
            displayName="Organizer"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token(subject=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(timezone.utc)

    # 1. End time <= Start time
    payload_invalid_order = {
        "title": "Invalid Order Event",
        "category": "Tech",
        "description": "A test event with end before start",
        "startTime": (now + timedelta(days=2)).isoformat(),
        "endTime": (now + timedelta(days=1)).isoformat(),
        "location": "Room 101",
        "maxParticipants": 5
    }
    res1 = await async_client.post("/api/events", json=payload_invalid_order, headers=headers)
    assert res1.status_code == 400
    assert "must be after" in res1.json()["detail"]

    # 2. End time in the past
    payload_past_end = {
        "title": "Past End Event",
        "category": "Tech",
        "description": "A test event with end time in the past",
        "startTime": (now - timedelta(days=2)).isoformat(),
        "endTime": (now - timedelta(days=1)).isoformat(),
        "location": "Room 101",
        "maxParticipants": 5
    }
    res2 = await async_client.post("/api/events", json=payload_past_end, headers=headers)
    assert res2.status_code == 400
    assert "cannot be in the past" in res2.json()["detail"]

    # 3. Valid event creation
    payload_valid = {
        "title": "Valid Future Event",
        "category": "Tech",
        "description": "A valid future event",
        "startTime": (now + timedelta(days=1, hours=10)).isoformat(),
        "endTime": (now + timedelta(days=1, hours=12)).isoformat(),
        "location": "Room 101",
        "maxParticipants": 5
    }
    res3 = await async_client.post("/api/events", json=payload_valid, headers=headers)
    assert res3.status_code == 201
    assert res3.json()["success"] is True

@pytest.mark.asyncio
async def test_recommendation_expiration(async_client: AsyncClient, setup_db):
    """
    Test that ended events (endTime <= now) do not appear in the recommended feed.
    """
    now = datetime.now(timezone.utc)
    async with TestingSessionLocal() as session:
        host = User(
            studentEmail="host@cput.ac.za",
            passwordHash="hashed",
            isVerified=True,
            displayName="Host",
            university="CPUT",
            yearOfStudy=2,
            age=21
        )
        session.add(host)
        await session.commit()
        await session.refresh(host)

        # Event in the past
        past_event = Event(
            title="Past Event",
            category="Tech",
            description="Event that concluded yesterday",
            startTime=now - timedelta(days=2),
            endTime=now - timedelta(days=1),
            location="Room Past",
            maxParticipants=5,
            hostId=host.id,
            status="ACTIVE"
        )
        # Event in the future
        future_event = Event(
            title="Upcoming Event",
            category="Tech",
            description="Event happening tomorrow",
            startTime=now + timedelta(days=1),
            endTime=now + timedelta(days=1, hours=2),
            location="Room Future",
            maxParticipants=5,
            hostId=host.id,
            status="ACTIVE"
        )
        session.add(past_event)
        session.add(future_event)

        # Viewer user
        viewer = User(
            studentEmail="viewer@cput.ac.za",
            passwordHash="hashed",
            isVerified=True,
            displayName="Viewer",
            university="CPUT",
            yearOfStudy=2,
            age=21,
            cachedVectorEmbedding=[0.1] * 768
        )
        session.add(viewer)
        await session.commit()
        await session.refresh(viewer)

    token = create_access_token(subject=str(viewer.id))
    headers = {"Authorization": f"Bearer {token}"}

    res = await async_client.get("/api/events?tab=recommended", headers=headers)
    assert res.status_code == 200
    events = res.json()["events"]
    event_titles = [e["title"] for e in events]

    assert "Past Event" not in event_titles
    assert "Upcoming Event" in event_titles

@pytest.mark.asyncio
async def test_cannot_join_ended_event_but_can_leave(async_client: AsyncClient, setup_db):
    """
    Test that:
    1. Users cannot join an ended event (400 Bad Request)
    2. Users who are already in an ended event CAN leave it (200 OK)
    """
    now = datetime.now(timezone.utc)
    async with TestingSessionLocal() as session:
        # Create an ended event
        ended_event = Event(
            title="Concluded Workshop",
            category="Tech",
            description="Ended yesterday",
            startTime=now - timedelta(days=2),
            endTime=now - timedelta(days=1),
            location="Room 0",
            maxParticipants=10,
            hostId=str(uuid.uuid4()),
            status="ACTIVE"
        )
        session.add(ended_event)
        
        # User 1: Already joined participant
        joined_user = User(
            studentEmail="joined_user@cput.ac.za",
            passwordHash="hashed",
            isVerified=True
        )
        # User 2: Non-joined user
        outsider_user = User(
            studentEmail="outsider@cput.ac.za",
            passwordHash="hashed",
            isVerified=True
        )
        session.add(joined_user)
        session.add(outsider_user)
        await session.commit()
        await session.refresh(ended_event)
        await session.refresh(joined_user)
        await session.refresh(outsider_user)

        # Add joined_user to ended_event
        p = EventParticipant(eventId=ended_event.id, userId=joined_user.id)
        session.add(p)
        await session.commit()

    token_outsider = create_access_token(subject=str(outsider_user.id))
    token_joined = create_access_token(subject=str(joined_user.id))

    # 1. Outsider attempts to join ended event -> Must be rejected (400)
    join_res = await async_client.post(
        f"/api/events/{ended_event.id}/join",
        headers={"Authorization": f"Bearer {token_outsider}"}
    )
    assert join_res.status_code == 400
    assert "already ended" in join_res.json()["detail"]

    # 2. Joined user attempts to leave ended event -> Must succeed (200)
    leave_res = await async_client.post(
        f"/api/events/{ended_event.id}/leave",
        headers={"Authorization": f"Bearer {token_joined}"}
    )
    assert leave_res.status_code == 200
    assert leave_res.json()["success"] is True

