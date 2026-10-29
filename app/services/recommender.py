import hashlib
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func
from sqlalchemy.orm import selectinload

from app.models.event import Event, EventParticipant
from app.models.user import User
from app.models.rationale import EventRationale
from app.services.llm_service import compute_cosine_similarity, generate_user_embedding, generate_batch_rationales

async def get_recommended_events(
    db: AsyncSession, 
    user: User, 
    page: int = 1, 
    limit: int = 6, 
    tab: str = "recommended", 
    category: str = "All"
):
    # Ensure user has embeddings
    if tab == "recommended" and not user.cachedVectorEmbedding:
        try:
            vector = await generate_user_embedding({
                "bio": user.bio,
                "interests": user.interests,
                "lookingForTags": user.lookingForTags,
                "languages": user.languages
            })
            if vector:
                user.cachedVectorEmbedding = vector
                db.add(user)
                await db.commit()
        except Exception:
            pass

    # Fetch all events with host and participants count
    result = await db.execute(
        select(Event)
        .options(selectinload(Event.host), selectinload(Event.participants))
        .order_by(Event.startTime)
    )
    events = result.scalars().all()

    # Get joined event IDs
    joined_events_result = await db.execute(
        select(EventParticipant.eventId).where(EventParticipant.userId == user.id)
    )
    joined_event_ids = joined_events_result.scalars().all()

    # Layer 1: Hard Filtering
    user_is_first_year = user.age and user.age <= 19 and user.yearOfStudy == 1
    
    filtered_events = []
    for event in events:
        if event.id in joined_event_ids or event.hostId == user.id:
            filtered_events.append(event)
            continue
            
        if user.university and event.host.university and user.university != event.host.university:
            continue
            
        host_is_first_year = event.host.age and event.host.age <= 19 and event.host.yearOfStudy == 1
        if user_is_first_year and not host_is_first_year:
            continue
        if not user_is_first_year and host_is_first_year:
            continue
            
        filtered_events.append(event)

    # Layer 2: Semantic Scoring
    scored_events = []
    user_tags_str = " ".join((user.lookingForTags or []) + (user.extractedAiTags or []) + (user.interests or [])).lower()
    
    for event in filtered_events:
        score = 50
        
        # Vector Similarity
        if user.cachedVectorEmbedding and event.cachedVectorEmbedding:
            sim = compute_cosine_similarity(user.cachedVectorEmbedding, event.cachedVectorEmbedding)
            score = round(sim * 100)
            
        # Category heuristic
        if event.category.lower() in user_tags_str:
            score += 10
            
        is_high_energy = event.category in ["Social", "Party", "Outdoors"]
        is_low_energy = event.category in ["Study", "Creative"]
        
        if user.socialEnergyLevel == "High" and is_high_energy: score += 5
        if user.socialEnergyLevel == "Low" and is_low_energy: score += 5
        
        # Host compatibility
        if event.hostId != user.id:
            if user.isInternationalStudent and event.host.isInternationalStudent: score += 15
            if user.university == event.host.university: score += 5
            if user.yearOfStudy == event.host.yearOfStudy: score += 5
            if user.age and event.host.age and abs(user.age - event.host.age) <= 2: score += 5
            
            shared_langs = set(user.languages or []) & set(event.host.languages or [])
            score += len(shared_langs) * 2
            
            shared_interests = set(user.interests or []) & set(event.host.interests or [])
            score += len(shared_interests) * 2
            
            if user.socialEnergyLevel == event.host.socialEnergyLevel: score += 5
            
        score = min(max(score, 10), 99)
        scored_events.append({"event": event, "score": score})

    scored_events.sort(key=lambda x: x["score"], reverse=True)

    # Filtering by Tab & Category
    final_filtered = []
    for item in scored_events:
        event = item["event"]
        is_joined = event.id in joined_event_ids
        is_host = event.hostId == user.id
        item["is_joined"] = is_joined
        item["is_host"] = is_host
        
        if tab == "my-events" and not is_joined: continue
        if tab == "created-events" and not is_host: continue
        if tab == "recommended" and (is_host or is_joined): continue
        if category != "All" and event.category != category: continue
        
        final_filtered.append(item)

    # Pagination
    total_count = len(final_filtered)
    paginated_events = final_filtered[(page - 1) * limit : page * limit]

    # Layer 3: LLM Rationale
    user_context = f"Age: {user.age}. Year of Study: {user.yearOfStudy}. University: {user.university}. Interests: {', '.join(user.interests or [])}. Languages: {', '.join(user.languages or [])}. Looking For: {', '.join(user.lookingForTags or [])}. Social Energy: {user.socialEnergyLevel} ({user.introvertExtrovertScore}/100). Bio: {user.bio}"
    user_profile_hash = hashlib.sha256(user_context.encode()).hexdigest()
    
    # Fetch existing rationales
    event_ids = [item["event"].id for item in paginated_events]
    rationales_result = await db.execute(
        select(EventRationale).where(EventRationale.userId == user.id, EventRationale.eventId.in_(event_ids))
    )
    rationale_map = {r.eventId: r for r in rationales_result.scalars().all()}
    
    batch_results = {}
    if tab == "recommended":
        cache_misses = []
        for item in paginated_events:
            event = item["event"]
            cached = rationale_map.get(event.id)
            if not cached or cached.userProfileHash != user_profile_hash:
                host_details = f"Host Age: {event.host.age}. Host Year of Study: {event.host.yearOfStudy}. Host University: {event.host.university}. Host Interests: {', '.join(event.host.interests or [])}. Host Languages: {', '.join(event.host.languages or [])}. Host Energy: {event.host.socialEnergyLevel}. Host Bio: {event.host.bio}"
                cache_misses.append({
                    "eventId": event.id,
                    "eventContext": f"Title: {event.title}. Category: {event.category}. Description: {event.description}. [HOST PROFILE]: {host_details}"
                })
        
        if cache_misses:
            batch_results = await generate_batch_rationales(user_context, cache_misses)
            
            # Upsert
            for e_id, rationale_text in batch_results.items():
                existing = rationale_map.get(e_id)
                if existing:
                    existing.rationale = rationale_text
                    existing.userProfileHash = user_profile_hash
                else:
                    new_rat = EventRationale(
                        eventId=e_id, userId=user.id, rationale=rationale_text, userProfileHash=user_profile_hash
                    )
                    db.add(new_rat)
                    rationale_map[e_id] = new_rat
            await db.commit()

    # Final assembly
    final_events = []
    for item in paginated_events:
        event = item["event"]
        score = item["score"]
        is_joined = item["is_joined"]
        is_host = item["is_host"]
        
        rationale = f"Recommended because this {event.category} event matches your interests."
        cached = rationale_map.get(event.id)
        
        if is_host:
            rationale = "You are hosting this event."
        elif is_joined:
            if cached: rationale = cached.rationale
            else: rationale = "You have joined this event."
        else:
            if cached and cached.userProfileHash == user_profile_hash:
                rationale = cached.rationale
            elif event.id in batch_results:
                rationale = batch_results[event.id]
            elif score > 80:
                rationale = "Highly recommended based on your AI-extracted profile matches and semantic similarity."
                
        # Format datetime
        d = event.startTime
        e = event.endTime
        day = f"{d.day:02d}/{d.month:02d}/{d.year}"
        e_day = f"{e.day:02d}/{e.month:02d}/{e.year}"
        
        formatted = f"{day} {d.hour:02d}:{d.minute:02d} - "
        if day == e_day:
            formatted += f"{e.hour:02d}:{e.minute:02d}"
        else:
            formatted += f"{e_day} {e.hour:02d}:{e.minute:02d}"
            
        participant_count = len(event.participants)
        dummy_avatars = [f"https://i.pravatar.cc/150?img={(i + 10) % 70}" for i in range(participant_count)]
        
        final_events.append({
            "id": event.id,
            "title": event.title,
            "category": event.category,
            "description": event.description,
            "datetime": formatted,
            "location": event.location,
            "capacity": event.maxParticipants,
            "joinedCount": participant_count,
            "similarity": score,
            "rationale": rationale,
            "participants": dummy_avatars,
            "isJoined": is_joined,
            "isHost": is_host
        })

    return {"events": final_events, "totalCount": total_count}

async def pregenerate_user_rationales(db: AsyncSession, user: User, limit: int = 6) -> int:
    """
    Pre-generates and caches 1-sentence Gemini match rationales for candidate events
    during profile save or onboarding, so loading /events is instant.
    """
    user_context = f"Age: {user.age}. Year of Study: {user.yearOfStudy}. University: {user.university}. Interests: {', '.join(user.interests or [])}. Languages: {', '.join(user.languages or [])}. Looking For: {', '.join(user.lookingForTags or [])}. Social Energy: {user.socialEnergyLevel} ({user.introvertExtrovertScore}/100). Bio: {user.bio}"
    user_profile_hash = hashlib.sha256(user_context.encode()).hexdigest()

    result = await db.execute(
        select(Event)
        .options(selectinload(Event.host), selectinload(Event.participants))
        .where(Event.status == "ACTIVE")
        .order_by(Event.startTime)
    )
    events = result.scalars().all()

    joined_events_result = await db.execute(
        select(EventParticipant.eventId).where(EventParticipant.userId == user.id)
    )
    joined_event_ids = set(joined_events_result.scalars().all())

    user_is_first_year = user.age and user.age <= 19 and user.yearOfStudy == 1
    candidate_events = []
    for event in events:
        if event.id in joined_event_ids or event.hostId == user.id:
            continue
        if user.university and event.host.university and user.university != event.host.university:
            continue
        host_is_first_year = event.host.age and event.host.age <= 19 and event.host.yearOfStudy == 1
        if user_is_first_year and not host_is_first_year:
            continue
        if not user_is_first_year and host_is_first_year:
            continue
        candidate_events.append(event)
        if len(candidate_events) >= limit:
            break

    if not candidate_events:
        return 0

    event_ids = [e.id for e in candidate_events]
    rationales_result = await db.execute(
        select(EventRationale).where(EventRationale.userId == user.id, EventRationale.eventId.in_(event_ids))
    )
    rationale_map = {r.eventId: r for r in rationales_result.scalars().all()}

    cache_misses = []
    for event in candidate_events:
        cached = rationale_map.get(event.id)
        if not cached or cached.userProfileHash != user_profile_hash:
            host_details = f"Host Age: {event.host.age}. Host Year of Study: {event.host.yearOfStudy}. Host University: {event.host.university}. Host Interests: {', '.join(event.host.interests or [])}. Host Languages: {', '.join(event.host.languages or [])}. Host Energy: {event.host.socialEnergyLevel}. Host Bio: {event.host.bio}"
            cache_misses.append({
                "eventId": event.id,
                "eventContext": f"Title: {event.title}. Category: {event.category}. Description: {event.description}. [HOST PROFILE]: {host_details}"
            })

    if not cache_misses:
        return 0

    batch_results = await generate_batch_rationales(user_context, cache_misses)
    count = 0
    for e_id, rationale_text in batch_results.items():
        existing = rationale_map.get(e_id)
        if existing:
            existing.rationale = rationale_text
            existing.userProfileHash = user_profile_hash
        else:
            new_rat = EventRationale(
                eventId=e_id, userId=user.id, rationale=rationale_text, userProfileHash=user_profile_hash
            )
            db.add(new_rat)
            rationale_map[e_id] = new_rat
        count += 1

    await db.commit()
    return count

