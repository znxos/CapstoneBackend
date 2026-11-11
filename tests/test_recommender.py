import pytest
from httpx import AsyncClient
from sqlmodel import select
from app.models.user import User
from app.models.event import Event, EventParticipant
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

@pytest.mark.asyncio
async def test_unjoined_filtering_in_recommended_tab(async_client: AsyncClient, setup_db):
    """
    Verify that an event joined by the user is excluded from 'recommended' and present in 'my-events'.
    """
    from app.models.event import EventParticipant

    async with TestingSessionLocal() as session:
        host = User(
            studentEmail="host2@cput.ac.za", 
            passwordHash="hashed", 
            isVerified=True,
            age=22,
            yearOfStudy=2,
            university="CPUT"
        )
        session.add(host)
        await session.commit()
        await session.refresh(host)

        user = User(
            studentEmail="student2@cput.ac.za", 
            passwordHash="hashed", 
            isVerified=True,
            age=22,
            yearOfStudy=2,
            university="CPUT"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        event = Event(
            title="Study Group",
            category="Study",
            description="Focus session",
            startTime=datetime.now(timezone.utc) + timedelta(hours=2),
            endTime=datetime.now(timezone.utc) + timedelta(hours=5),
            location="Library Room A",
            maxParticipants=5,
            hostId=host.id,
            status="ACTIVE"
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)

        # User joins the event
        participant = EventParticipant(eventId=event.id, userId=user.id)
        session.add(participant)
        await session.commit()

    token = create_access_token(subject=str(user.id), expires_delta=timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {token}"}

    # Recommended feed: joined event MUST NOT appear
    rec_res = await async_client.get("/api/events?tab=recommended", headers=headers)
    assert rec_res.status_code == 200
    rec_ids = [e["id"] for e in rec_res.json().get("events", [])]
    assert event.id not in rec_ids

    # My Events feed: joined event MUST appear
    my_res = await async_client.get("/api/events?tab=my-events", headers=headers)
    assert my_res.status_code == 200
    my_ids = [e["id"] for e in my_res.json().get("events", [])]
    assert event.id in my_ids
    assert my_res.json()["events"][0]["rationale"] == "You have joined this event."

@pytest.mark.asyncio
async def test_ai_reranker_and_cache_hit(async_client: AsyncClient, setup_db):
    """
    Verify that EventRationale cache hit returns the cached AI score and rationale without re-calling the LLM.
    """
    from app.models.rationale import EventRationale
    from app.services.recommender import compute_user_profile_hash

    async with TestingSessionLocal() as session:
        host = User(
            studentEmail="host3@cput.ac.za", 
            passwordHash="hashed", 
            isVerified=True,
            age=20,
            yearOfStudy=2,
            university="CPUT",
            bio="Host bio"
        )
        session.add(host)
        await session.commit()
        await session.refresh(host)

        user = User(
            studentEmail="student3@cput.ac.za", 
            passwordHash="hashed", 
            isVerified=True,
            age=20,
            yearOfStudy=2,
            university="CPUT",
            interests=["Coding"],
            languages=["English"],
            lookingForTags=["Study Partners"],
            socialEnergyLevel="Medium",
            introvertExtrovertScore=50,
            bio="Love coding",
            cachedVectorEmbedding=[0.1] * 768
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        event = Event(
            title="Python Hack Night",
            category="Tech",
            description="Building fast APIs",
            startTime=datetime.now(timezone.utc) + timedelta(hours=3),
            endTime=datetime.now(timezone.utc) + timedelta(hours=6),
            location="Lab 3",
            maxParticipants=10,
            hostId=host.id,
            status="ACTIVE",
            cachedVectorEmbedding=[0.1] * 768
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)

        expected_hash = compute_user_profile_hash(user)

        # Seed cached rationale with high AI score
        cached_rat = EventRationale(
            eventId=event.id,
            userId=user.id,
            score=96,
            rationale="Recommended because you both love Python and share medium energy.",
            userProfileHash=expected_hash
        )
        session.add(cached_rat)
        await session.commit()

    token = create_access_token(subject=str(user.id), expires_delta=timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {token}"}

    res = await async_client.get("/api/events?tab=recommended", headers=headers)
    assert res.status_code == 200
    events = res.json().get("events", [])
    matching = [e for e in events if e["id"] == event.id]
    assert len(matching) == 1
    assert matching[0]["similarity"] == 96
    assert matching[0]["rationale"] == "Recommended because you both love Python and share medium energy."

@pytest.mark.asyncio
async def test_joined_events_sorted_by_most_recently_joined(async_client: AsyncClient, setup_db):
    """
    Verify that the 'my-events' tab returns joined events in descending order of joinedAt (most recently joined first).
    """
    now = datetime.now(timezone.utc)
    async with TestingSessionLocal() as session:
        user = User(
            studentEmail="joiner_sort@cput.ac.za",
            passwordHash="hashed",
            isVerified=True,
            university="CPUT",
            yearOfStudy=3,
            age=21,
            cachedVectorEmbedding=[0.1] * 768
        )
        host = User(
            studentEmail="sort_host@cput.ac.za",
            passwordHash="hashed",
            isVerified=True,
            university="CPUT",
            yearOfStudy=3,
            age=22,
            cachedVectorEmbedding=[0.1] * 768
        )
        session.add_all([user, host])
        await session.commit()
        await session.refresh(user)
        await session.refresh(host)

        # Event A: Starts in 2 days
        event_a = Event(
            title="Event A (Earliest Start)",
            category="Tech",
            description="Event A description",
            startTime=now + timedelta(days=2),
            endTime=now + timedelta(days=2, hours=2),
            location="Lab 1",
            maxParticipants=10,
            hostId=host.id,
            status="ACTIVE"
        )
        # Event B: Starts in 5 days
        event_b = Event(
            title="Event B (Middle Start)",
            category="Tech",
            description="Event B description",
            startTime=now + timedelta(days=5),
            endTime=now + timedelta(days=5, hours=2),
            location="Lab 2",
            maxParticipants=10,
            hostId=host.id,
            status="ACTIVE"
        )
        # Event C: Starts in 10 days
        event_c = Event(
            title="Event C (Latest Start)",
            category="Tech",
            description="Event C description",
            startTime=now + timedelta(days=10),
            endTime=now + timedelta(days=10, hours=2),
            location="Lab 3",
            maxParticipants=10,
            hostId=host.id,
            status="ACTIVE"
        )
        session.add_all([event_a, event_b, event_c])
        await session.commit()
        await session.refresh(event_a)
        await session.refresh(event_b)
        await session.refresh(event_c)

        # Join Event B first (2 hours ago)
        p_b = EventParticipant(
            eventId=event_b.id,
            userId=user.id,
            joinedAt=now - timedelta(hours=2)
        )
        # Join Event C second (1 hour ago)
        p_c = EventParticipant(
            eventId=event_c.id,
            userId=user.id,
            joinedAt=now - timedelta(hours=1)
        )
        # Join Event A third (most recently: 5 minutes ago)
        p_a = EventParticipant(
            eventId=event_a.id,
            userId=user.id,
            joinedAt=now - timedelta(minutes=5)
        )
        session.add_all([p_b, p_c, p_a])
        await session.commit()

    token = create_access_token(subject=str(user.id), expires_delta=timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {token}"}

    res = await async_client.get("/api/events?tab=my-events", headers=headers)
    assert res.status_code == 200
    returned_events = res.json().get("events", [])
    returned_ids = [e["id"] for e in returned_events]

    # Must be ordered by joinedAt DESC: Event A (5m ago), Event C (1h ago), Event B (2h ago)
    assert returned_ids == [event_a.id, event_c.id, event_b.id]

@pytest.mark.asyncio
async def test_strict_campus_isolation(async_client: AsyncClient, setup_db):
    """
    Verify strict campus boundaries:
    A student from CPUT should ONLY see events hosted by CPUT students.
    Events hosted by UCT students or hosts with no university set must be filtered out.
    """
    now = datetime.now(timezone.utc)
    async with TestingSessionLocal() as session:
        # CPUT Host & Event
        cput_host = User(
            studentEmail="cput_host@cput.ac.za",
            passwordHash="hashed",
            isVerified=True,
            age=22,
            yearOfStudy=3,
            university="CPUT"
        )
        # UCT Host & Event
        uct_host = User(
            studentEmail="uct_host@myuct.ac.za",
            passwordHash="hashed",
            isVerified=True,
            age=22,
            yearOfStudy=3,
            university="UCT"
        )
        # Unassigned Host & Event
        no_uni_host = User(
            studentEmail="no_uni@cput.ac.za",
            passwordHash="hashed",
            isVerified=True,
            age=22,
            yearOfStudy=3,
            university=None
        )
        session.add_all([cput_host, uct_host, no_uni_host])
        await session.commit()
        await session.refresh(cput_host)
        await session.refresh(uct_host)
        await session.refresh(no_uni_host)

        cput_event = Event(
            title="CPUT Robotics Workshop",
            category="Tech",
            description="Robotics on Bellville campus",
            startTime=now + timedelta(days=2),
            endTime=now + timedelta(days=2, hours=2),
            location="CPUT Lab 1",
            maxParticipants=10,
            hostId=cput_host.id,
            status="ACTIVE"
        )
        uct_event = Event(
            title="UCT Coding Hackathon",
            category="Tech",
            description="Hackathon on Rondebosch campus",
            startTime=now + timedelta(days=3),
            endTime=now + timedelta(days=3, hours=2),
            location="UCT CS Lab",
            maxParticipants=10,
            hostId=uct_host.id,
            status="ACTIVE"
        )
        no_uni_event = Event(
            title="General Campus Hangout",
            category="Social",
            description="Casual hangout",
            startTime=now + timedelta(days=4),
            endTime=now + timedelta(days=4, hours=2),
            location="Campus Lawn",
            maxParticipants=10,
            hostId=no_uni_host.id,
            status="ACTIVE"
        )
        session.add_all([cput_event, uct_event, no_uni_event])

        # Create CPUT viewing user
        cput_viewer = User(
            studentEmail="viewer@cput.ac.za",
            passwordHash="hashed",
            isVerified=True,
            age=22,
            yearOfStudy=3,
            university="CPUT"
        )
        session.add(cput_viewer)
        await session.commit()
        await session.refresh(cput_viewer)
        await session.refresh(cput_event)
        await session.refresh(uct_event)
        await session.refresh(no_uni_event)

    token = create_access_token(subject=str(cput_viewer.id), expires_delta=timedelta(minutes=15))
    headers = {"Authorization": f"Bearer {token}"}

    res = await async_client.get("/api/events?tab=recommended", headers=headers)
    assert res.status_code == 200
    events = res.json().get("events", [])
    returned_ids = [e["id"] for e in events]

    # Only CPUT event should be returned; UCT and unassigned events must be excluded
    assert cput_event.id in returned_ids
    assert uct_event.id not in returned_ids
    assert no_uni_event.id not in returned_ids

