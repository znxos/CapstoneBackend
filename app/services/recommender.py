import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.models.event import Event, EventParticipant
from app.models.user import User
from app.models.rationale import EventRationale
from app.services.llm_service import (
    compute_cosine_similarity, 
    generate_user_embedding, 
    rerank_and_rationalize_events
)

def format_event_datetime(start_dt: datetime, end_dt: datetime) -> str:
    d = start_dt
    e = end_dt
    day = f"{d.day:02d}/{d.month:02d}/{d.year}"
    e_day = f"{e.day:02d}/{e.month:02d}/{e.year}"
    
    formatted = f"{day} {d.hour:02d}:{d.minute:02d} - "
    if day == e_day:
        formatted += f"{e.hour:02d}:{e.minute:02d}"
    else:
        formatted += f"{e_day} {e.hour:02d}:{e.minute:02d}"
    return formatted

def compute_user_profile_context(user: User) -> str:
    return (
        f"Age: {user.age}. Year of Study: {user.yearOfStudy}. University: {user.university}. "
        f"Interests: {', '.join(user.interests or [])}. Languages: {', '.join(user.languages or [])}. "
        f"Looking For: {', '.join(user.lookingForTags or [])}. AI Tags: {', '.join(user.extractedAiTags or [])}. "
        f"Social Energy: {user.socialEnergyLevel} ({user.introvertExtrovertScore}/100). Bio: {user.bio}"
    )

def compute_user_profile_hash(user: User) -> str:
    ctx = compute_user_profile_context(user)
    return hashlib.sha256(ctx.encode()).hexdigest()

async def get_recommended_events(
    db: AsyncSession, 
    user: User, 
    page: int = 1, 
    limit: int = 6, 
    tab: str = "recommended", 
    category: str = "All",
    generate_more: bool = False
):
    # Ensure user has vector embeddings
    if tab == "recommended" and not user.cachedVectorEmbedding:
        try:
            vector = await generate_user_embedding({
                "bio": user.bio,
                "interests": user.interests,
                "lookingForTags": user.lookingForTags,
                "extractedAiTags": user.extractedAiTags,
                "languages": user.languages
            })
            if vector:
                user.cachedVectorEmbedding = vector
                db.add(user)
                await db.commit()
        except Exception as e:
            print(f"Error generating user embedding: {e}")

    # Fetch all events with host and participants
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.host), selectinload(Event.participants))
        .order_by(Event.startTime)
    )
    events = result.scalars().all()

    # Get joined event IDs and joinedAt timestamps
    joined_events_result = await db.execute(
        select(EventParticipant.eventId, EventParticipant.joinedAt).where(EventParticipant.userId == user.id)
    )
    joined_participant_rows = joined_events_result.all()
    joined_event_map = {row[0]: row[1] for row in joined_participant_rows}
    joined_event_ids = set(joined_event_map.keys())

    # Layer 1: Tab-Aware Hard Filtering
    now = datetime.now(timezone.utc)
    user_is_first_year = bool(user.age and user.age <= 19 and user.yearOfStudy == 1)
    
    eligible_events: List[Event] = []
    for event in events:
        event_end = event.endTime if (event.endTime and event.endTime.tzinfo) else (event.endTime.replace(tzinfo=timezone.utc) if event.endTime else now)
        is_ended = event_end <= now

        is_joined = event.id in joined_event_ids
        is_host = event.hostId == user.id

        if tab == "recommended":
            # Exclude ended or inactive events
            if is_ended or event.status != "ACTIVE":
                continue
            # EXCLUDE joined and hosted events immediately so event slots are 100% unjoined
            if is_joined or is_host:
                continue
            # Campus boundaries
            if user.university:
                host_uni = (event.host.university or "").strip().upper() if event.host else ""
                if host_uni != user.university.strip().upper():
                    continue

            # First-year restriction to help protect them, they may not join events hosted by individuals outside their year.
            host_is_first_year = bool(
                event.host 
                and event.host.age 
                and event.host.age <= 19 
                and event.host.yearOfStudy == 1
            )
            if user_is_first_year != host_is_first_year:
                continue
            # Category filter
            if category != "All" and event.category != category:
                continue

            eligible_events.append(event)

        elif tab == "my-events":
            if not is_joined:
                continue
            if category != "All" and event.category != category:
                continue
            eligible_events.append(event)

        elif tab == "created-events":
            if not is_host:
                continue
            if category != "All" and event.category != category:
                continue
            eligible_events.append(event)

    # If non-recommended tabs: Simple chronological list with fixed labels (0 AI calls)
    if tab != "recommended":
        if tab == "my-events":
            # Most recently joined events first
            def get_joined_time(ev: Event):
                t = joined_event_map.get(ev.id)
                if not t:
                    return datetime.min.replace(tzinfo=timezone.utc)
                if t.tzinfo is None:
                    return t.replace(tzinfo=timezone.utc)
                return t

            eligible_events.sort(key=get_joined_time, reverse=True)

        total_count = len(eligible_events)
        paginated_events = eligible_events[(page - 1) * limit : page * limit]
        
        final_events = []
        for event in paginated_events:
            is_joined = event.id in joined_event_ids
            is_host = event.hostId == user.id
            rationale = "You are hosting this event." if is_host else "You have joined this event."
            
            event_end = event.endTime if (event.endTime and event.endTime.tzinfo) else (event.endTime.replace(tzinfo=timezone.utc) if event.endTime else now)
            is_ended = event_end <= now
            
            participant_count = len(event.participants)
            dummy_avatars = [f"https://i.pravatar.cc/150?img={(i + 10) % 70}" for i in range(participant_count)]
            
            final_events.append({
                "id": event.id,
                "title": event.title,
                "category": event.category,
                "description": event.description,
                "datetime": format_event_datetime(event.startTime, event.endTime),
                "location": event.location,
                "capacity": event.maxParticipants,
                "joinedCount": participant_count,
                "similarity": 100 if is_host else 90,
                "rationale": rationale,
                "participants": dummy_avatars,
                "isJoined": is_joined,
                "isHost": is_host,
                "isEnded": is_ended,
            })
        return {"events": final_events, "totalCount": total_count, "hasMoreMatches": False}

    # RECOMMENDED TAB: Two-Stage Retrieve & Re-Rank Engine
    total_count = len(eligible_events)
    if not eligible_events:
        return {"events": [], "totalCount": 0, "hasMoreMatches": False}

    # Stage 1: Vector Cosine Baseline Scoring for all eligible unjoined events
    scored_items: List[Dict[str, Any]] = []
    user_tags_str = " ".join((user.lookingForTags or []) + (user.extractedAiTags or []) + (user.interests or [])).lower()

    for event in eligible_events:
        baseline_score = 50
        if user.cachedVectorEmbedding and event.cachedVectorEmbedding:
            sim = compute_cosine_similarity(user.cachedVectorEmbedding, event.cachedVectorEmbedding)
            baseline_score = round(sim * 100)
            
        # Quick heuristic adjustment for baseline retrieval ranking
        if event.category.lower() in user_tags_str:
            baseline_score += 5
        if event.host and user.socialEnergyLevel == event.host.socialEnergyLevel:
            baseline_score += 3
        if event.host and user.yearOfStudy == event.host.yearOfStudy:
            baseline_score += 3
            
        baseline_score = min(max(baseline_score, 10), 99)
        scored_items.append({
            "event": event,
            "baseline_score": baseline_score,
            "score": baseline_score,
            "is_joined": False,
            "is_host": False
        })

    # Sort all eligible items by baseline similarity
    scored_items.sort(key=lambda x: x["baseline_score"], reverse=True)

    # Default is 12 candidates (covers Pages 1 & 2). If generate_more requested on last page, expands by another 12.
    target_pool_size = (page * limit) + 12 if generate_more else max(page * limit, 12)
    target_pool_size = min(target_pool_size, len(scored_items))
    
    candidates_to_rerank = scored_items[:target_pool_size]

    # Stage 2: Cache Check & LLM Re-Ranking
    user_context = compute_user_profile_context(user)
    user_profile_hash = compute_user_profile_hash(user)

    candidate_ids = [c["event"].id for c in candidates_to_rerank]
    rationales_result = await db.execute(
        select(EventRationale).where(
            EventRationale.userId == user.id, 
            EventRationale.eventId.in_(candidate_ids)
        )
    )
    rationale_map = {r.eventId: r for r in rationales_result.scalars().all()}

    cache_misses = []
    for c in candidates_to_rerank:
        event = c["event"]
        cached = rationale_map.get(event.id)
        # Cache hit requires matching hash AND a non-null AI score
        if not cached or cached.userProfileHash != user_profile_hash or cached.score is None:
            host = event.host
            host_details = (
                f"Host Age: {host.age}. Host Year: {host.yearOfStudy}. Host University: {host.university}. "
                f"Host Interests: {', '.join(host.interests or [])}. Host Languages: {', '.join(host.languages or [])}. "
                f"Host Energy: {host.socialEnergyLevel}. Host Bio: {host.bio}"
            )
            cache_misses.append({
                "eventId": event.id,
                "eventContext": f"Title: {event.title}. Category: {event.category}. Description: {event.description}. [HOST PROFILE]: {host_details}",
                "baselineScore": c["baseline_score"]
            })
        else:
            c["score"] = cached.score
            c["rationale"] = cached.rationale

    # If any cache misses, query Gemini Flash in a single batch
    if cache_misses:
        batch_results = await rerank_and_rationalize_events(user_context, cache_misses)
        if batch_results:
            for e_id, data in batch_results.items():
                score = data.get("score", 70)
                rationale_text = data.get("rationale", "")
                existing = rationale_map.get(e_id)
                if existing:
                    existing.score = score
                    existing.rationale = rationale_text
                    existing.userProfileHash = user_profile_hash
                else:
                    new_rat = EventRationale(
                        eventId=e_id,
                        userId=user.id,
                        score=score,
                        rationale=rationale_text,
                        userProfileHash=user_profile_hash
                    )
                    db.add(new_rat)
                    rationale_map[e_id] = new_rat
            await db.commit()

    # Populate final score and rationale onto candidate items
    for c in candidates_to_rerank:
        event = c["event"]
        cached = rationale_map.get(event.id)
        if cached and cached.score is not None:
            c["score"] = cached.score
            c["rationale"] = cached.rationale
        elif "rationale" not in c or not c.get("rationale"):
            # Resilient fallback if LLM is rate-limited or unavailable
            c["rationale"] = f"Recommended based on your interest in {event.category} events."

    # Re-sort the AI-evaluated candidate pool by AI score
    candidates_to_rerank.sort(key=lambda x: x["score"], reverse=True)

    # Re-assemble the full list: AI-reranked pool first, followed by remaining baseline vector items
    for item in scored_items[target_pool_size:]:
        if "rationale" not in item:
            item["rationale"] = f"Recommended based on topic alignment with {item['event'].category}."

    final_ordered_items = candidates_to_rerank + scored_items[target_pool_size:]

    # Apply pagination
    paginated_items = final_ordered_items[(page - 1) * limit : page * limit]

    # Format output
    final_events = []
    for item in paginated_items:
        event = item["event"]
        score = item["score"]
        rationale = item.get("rationale", f"Recommended because this {event.category} event matches your interests.")

        participant_count = len(event.participants)
        dummy_avatars = [f"https://i.pravatar.cc/150?img={(i + 10) % 70}" for i in range(participant_count)]

        event_end = event.endTime if (event.endTime and event.endTime.tzinfo) else (event.endTime.replace(tzinfo=timezone.utc) if event.endTime else now)
        is_ended = event_end <= now

        final_events.append({
            "id": event.id,
            "title": event.title,
            "category": event.category,
            "description": event.description,
            "datetime": format_event_datetime(event.startTime, event.endTime),
            "location": event.location,
            "capacity": event.maxParticipants,
            "joinedCount": participant_count,
            "similarity": score,
            "rationale": rationale,
            "participants": dummy_avatars,
            "isJoined": False,
            "isHost": False,
            "isEnded": is_ended,
        })

    has_more = target_pool_size < len(scored_items)
    return {"events": final_events, "totalCount": total_count, "hasMoreMatches": has_more}

async def pregenerate_user_rationales(db: AsyncSession, user: User, limit: int = 12) -> int:
    """
    Pre-generates and caches Gemini match scores and rationales for candidate unjoined events
    during profile save or onboarding, so loading /events is instant (<10ms).
    """
    user_context = compute_user_profile_context(user)
    user_profile_hash = compute_user_profile_hash(user)

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.host), selectinload(Event.participants))
        .where(Event.status == "ACTIVE", Event.endTime > now)
        .order_by(Event.startTime)
    )
    events = result.scalars().all()

    joined_events_result = await db.execute(
        select(EventParticipant.eventId).where(EventParticipant.userId == user.id)
    )
    joined_event_ids = set(joined_events_result.scalars().all())

    user_is_first_year = bool(user.age and user.age <= 19 and user.yearOfStudy == 1)
    eligible_events = []
    for event in events:
        if event.id in joined_event_ids or event.hostId == user.id:
            continue
        if user.university and event.host.university and user.university != event.host.university:
            continue
        host_is_first_year = bool(event.host.age and event.host.age <= 19 and event.host.yearOfStudy == 1)
        if user_is_first_year != host_is_first_year:
            continue
        eligible_events.append(event)

    if not eligible_events:
        return 0

    # Score by baseline vector similarity
    scored = []
    for event in eligible_events:
        baseline_score = 50
        if user.cachedVectorEmbedding and event.cachedVectorEmbedding:
            sim = compute_cosine_similarity(user.cachedVectorEmbedding, event.cachedVectorEmbedding)
            baseline_score = round(sim * 100)
        scored.append((event, baseline_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    candidate_events = [x[0] for x in scored[:limit]]

    event_ids = [e.id for e in candidate_events]
    rationales_result = await db.execute(
        select(EventRationale).where(EventRationale.userId == user.id, EventRationale.eventId.in_(event_ids))
    )
    rationale_map = {r.eventId: r for r in rationales_result.scalars().all()}

    cache_misses = []
    for event in candidate_events:
        cached = rationale_map.get(event.id)
        if not cached or cached.userProfileHash != user_profile_hash or cached.score is None:
            host = event.host
            host_details = (
                f"Host Age: {host.age}. Host Year of Study: {host.yearOfStudy}. Host University: {host.university}. "
                f"Host Interests: {', '.join(host.interests or [])}. Host Languages: {', '.join(host.languages or [])}. "
                f"Host Energy: {host.socialEnergyLevel}. Host Bio: {host.bio}"
            )
            cache_misses.append({
                "eventId": event.id,
                "eventContext": f"Title: {event.title}. Category: {event.category}. Description: {event.description}. [HOST PROFILE]: {host_details}"
            })

    if not cache_misses:
        return 0

    batch_results = await rerank_and_rationalize_events(user_context, cache_misses)
    count = 0
    for e_id, data in batch_results.items():
        score = data.get("score", 70)
        rationale_text = data.get("rationale", "")
        existing = rationale_map.get(e_id)
        if existing:
            existing.score = score
            existing.rationale = rationale_text
            existing.userProfileHash = user_profile_hash
        else:
            new_rat = EventRationale(
                eventId=e_id, 
                userId=user.id, 
                score=score,
                rationale=rationale_text, 
                userProfileHash=user_profile_hash
            )
            db.add(new_rat)
            rationale_map[e_id] = new_rat
        count += 1

    await db.commit()
    return count
