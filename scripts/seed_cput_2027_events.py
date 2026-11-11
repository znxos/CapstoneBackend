import asyncio
import random
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone, timedelta
from sqlmodel import select
from app.db.session import async_session
from app.models.user import User
from app.models.event import Event, EventParticipant
from app.services.llm_service import generate_event_embedding

CPUT_EVENT_BLUEPRINTS = [
    # Tech
    {
        "title": "Cloud Architecture & Docker Containers Workshop",
        "category": "Tech",
        "description": "Hands-on containerization and Kubernetes deployment sprint. Bring your laptop and learn to deploy scalable microservices.",
        "location": "CPUT Bellville IT Building Lab 2.01",
        "capacity": 8,
        "days_ahead": 130,
        "duration_hours": 3
    },
    {
        "title": "React Native Mobile App Hackathon",
        "category": "Tech",
        "description": "Collaborative mobile app build day. We will design and code a cross-platform campus utility app from scratch.",
        "location": "CPUT Cape Town Campus IT Lab 3",
        "capacity": 7,
        "days_ahead": 135,
        "duration_hours": 4
    },
    {
        "title": "Data Science & Pandas Machine Learning Sprint",
        "category": "Tech",
        "description": "Analyzing open campus datasets with Python, Pandas, Seaborn, and Scikit-Learn. Beginner-friendly walk-throughs included.",
        "location": "CPUT Engineering Building Lab 4",
        "capacity": 6,
        "days_ahead": 140,
        "duration_hours": 3
    },
    {
        "title": "Web3 & Smart Contract Security Audit Jam",
        "category": "Tech",
        "description": "Peer code review of Solidity smart contracts, spotting reentrancy vulnerabilities, and learning DeFi security best practices.",
        "location": "CPUT Bellville Library Study Room 2",
        "capacity": 6,
        "days_ahead": 145,
        "duration_hours": 3
    },
    {
        "title": "Linux Terminal Mastery & Bash Scripting",
        "category": "Tech",
        "description": "Level up your command line skills with regex, pipes, bash automation scripts, and server admin essentials.",
        "location": "CPUT Bellville IT Building Lab 1.05",
        "capacity": 8,
        "days_ahead": 150,
        "duration_hours": 2
    },

    # Study
    {
        "title": "Applied Calculus & Linear Algebra Cram Session",
        "category": "Study",
        "description": "Working through past papers, eigenvalues, matrix transformations, and multi-variable integration in a focused group.",
        "location": "CPUT Bellville Maths Study Hall",
        "capacity": 6,
        "days_ahead": 132,
        "duration_hours": 3
    },
    {
        "title": "Software Engineering Design Patterns Review",
        "category": "Study",
        "description": "Deep dive into Factory, Observer, Singleton, and Strategy patterns with UML diagrams and practical code implementations.",
        "location": "CPUT Cape Town Campus Library Quiet Room",
        "capacity": 6,
        "days_ahead": 138,
        "duration_hours": 3
    },
    {
        "title": "Network Engineering CCNA Practice Lab",
        "category": "Study",
        "description": "Cisco Packet Tracer subnetting drills, VLAN configurations, and routing protocol troubleshooting with senior peers.",
        "location": "CPUT Bellville Cisco Lab",
        "capacity": 6,
        "days_ahead": 142,
        "duration_hours": 3
    },
    {
        "title": "Database Systems & SQL Query Optimization Sprint",
        "category": "Study",
        "description": "Mastering indexing, execution plans, normalization, and complex joins for relational database management systems.",
        "location": "CPUT Cape Town Commerce Lab B",
        "capacity": 6,
        "days_ahead": 148,
        "duration_hours": 2
    },
    {
        "title": "Project Management & Agile Sprint Planning Prep",
        "category": "Study",
        "description": "Scrum methodology, user story mapping, burn-down charts, and capstone deliverable review session.",
        "location": "CPUT Bellville Seminar Room 3",
        "capacity": 7,
        "days_ahead": 155,
        "duration_hours": 2
    },

    # Social
    {
        "title": "Campus Chess & Speed Match Tournament",
        "category": "Social",
        "description": "Casual blitz and rapid chess matches. Boards and timers provided. Players of all ELO ratings welcome!",
        "location": "CPUT Student Centre Lounge 1",
        "capacity": 8,
        "days_ahead": 131,
        "duration_hours": 3
    },
    {
        "title": "Sunset Acoustic Jam & Open Mic",
        "category": "Social",
        "description": "Bring your guitar, ukulele, or just your voice. Casual unplugged jam session and lyric sharing on the student lawn.",
        "location": "CPUT Amphitheatre Lawn",
        "capacity": 8,
        "days_ahead": 136,
        "duration_hours": 3
    },
    {
        "title": "International Student Tea & Coffee Cultural Meet",
        "category": "Social",
        "description": "Share traditional snacks, teas, and stories from your hometown. A relaxed meetup to make cross-faculty friends.",
        "location": "CPUT International Student Office Lounge",
        "capacity": 8,
        "days_ahead": 141,
        "duration_hours": 2
    },
    {
        "title": "Retro Video Game & Mario Kart Arcade Night",
        "category": "Social",
        "description": "Nintendo Switch & retro emulator tournament on the big screen projector. Friendly competition and snacks provided.",
        "location": "CPUT Student Centre Media Room",
        "capacity": 8,
        "days_ahead": 147,
        "duration_hours": 3
    },
    {
        "title": "Language Exchange & Conversational French / IsiXhosa",
        "category": "Social",
        "description": "Practice conversational languages over tea with native speakers in a fun, non-academic setting.",
        "location": "CPUT Cape Town Student Cafeteria Annex",
        "capacity": 7,
        "days_ahead": 152,
        "duration_hours": 2
    },

    # Outdoors
    {
        "title": "Signal Hill Sunset Hike & Photography Walk",
        "category": "Outdoors",
        "description": "Scenic afternoon hike up Signal Hill for golden hour photography and panoramic ocean views. Bring water and sneakers.",
        "location": "Signal Hill Trailhead (Carpool from CPUT)",
        "capacity": 8,
        "days_ahead": 133,
        "duration_hours": 3
    },
    {
        "title": "Muizenberg Morning Beach Run & Dip",
        "category": "Outdoors",
        "description": "Energizing 5km coastal jog followed by a quick surf/swim and coffee at the beachside stalls.",
        "location": "Muizenberg Beach Pavilion",
        "capacity": 6,
        "days_ahead": 139,
        "duration_hours": 2
    },
    {
        "title": "Table Mountain Contour Trail Nature Walk",
        "category": "Outdoors",
        "description": "Relaxed fynbos botanical trail walk along the Table Mountain lower contour path. Great for fresh air and clearing your head.",
        "location": "Kloof Nek Parking Lot",
        "capacity": 7,
        "days_ahead": 146,
        "duration_hours": 3
    },
    {
        "title": "Campus 3v3 Basketball Pickup Games",
        "category": "Outdoors",
        "description": "Friendly half-court pickup basketball games. All skill levels welcome for cardio and team fun.",
        "location": "CPUT Outdoor Basketball Courts",
        "capacity": 8,
        "days_ahead": 151,
        "duration_hours": 2
    },
    {
        "title": "Sea Point Promenade Longboard & Rollerblade Cruise",
        "category": "Outdoors",
        "description": "Cruising along the Atlantic seaboard promenade. Bring your board, skates, or just walk along and enjoy the sea breeze.",
        "location": "Sea Point Swimming Pool Promenade",
        "capacity": 6,
        "days_ahead": 156,
        "duration_hours": 2
    },

    # Creative
    {
        "title": "Digital Illustration & Procreate Character Design",
        "category": "Creative",
        "description": "Bring your iPad or graphics tablet. We will design original concept characters, line art, and color palettes together.",
        "location": "CPUT Graphic Design Studio 2",
        "capacity": 6,
        "days_ahead": 134,
        "duration_hours": 3
    },
    {
        "title": "Street Photography & Urban Architecture Photo Walk",
        "category": "Creative",
        "description": "Exploring Cape Town city center architectural textures, street art, and candid urban moments with DSLR or phone cameras.",
        "location": "CPUT Cape Town Campus Front Steps",
        "capacity": 6,
        "days_ahead": 143,
        "duration_hours": 3
    },
    {
        "title": "Creative Writing & Flash Fiction Workshop",
        "category": "Creative",
        "description": "Timed writing prompts, character monologue exercises, and supportive peer feedback in a relaxed creative circle.",
        "location": "CPUT Bellville Library Seminar Room 1",
        "capacity": 6,
        "days_ahead": 149,
        "duration_hours": 2
    },
    {
        "title": "Film Lovers & Indie Cinema Discussion Circle",
        "category": "Creative",
        "description": "Watching and deconstructing classic cinema scenes, cinematography techniques, score composition, and narrative structure.",
        "location": "CPUT Media Arts Screening Room",
        "capacity": 8,
        "days_ahead": 154,
        "duration_hours": 3
    },
    {
        "title": "Ceramic Mug Painting & Pottery Social",
        "category": "Creative",
        "description": "Custom hand-painting ceramic mugs and coasters using underglazes and acrylic markers. Relaxing and mindful art session.",
        "location": "CPUT Fine Arts Studio 3",
        "capacity": 6,
        "days_ahead": 158,
        "duration_hours": 3
    }
]

async def seed():
    async with async_session() as session:
        # Find CPUT users who can be hosts
        cput_users = (await session.execute(
            select(User).where(User.university == "CPUT")
        )).scalars().all()

        if not cput_users:
            print("No CPUT users found to host events.")
            return

        now = datetime.now(timezone.utc)
        created_count = 0

        for bp in CPUT_EVENT_BLUEPRINTS:
            # Pick a host whose age/year is suitable
            host = random.choice(cput_users)
            
            start_time = now + timedelta(days=bp["days_ahead"], hours=random.choice([10, 14, 16, 18]))
            start_time = start_time.replace(minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(hours=bp["duration_hours"])

            print(f"Creating: '{bp['title']}' ({bp['category']})...")
            try:
                vector = await generate_event_embedding({
                    "title": bp["title"],
                    "category": bp["category"],
                    "description": bp["description"]
                })
            except Exception as e:
                vector = [0.0] * 768

            event = Event(
                title=bp["title"],
                category=bp["category"],
                description=bp["description"],
                startTime=start_time,
                endTime=end_time,
                location=bp["location"],
                maxParticipants=bp["capacity"],
                hostId=host.id,
                cachedVectorEmbedding=vector,
                status="ACTIVE"
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)

            # Host joins automatically
            host_participant = EventParticipant(eventId=event.id, userId=host.id)
            session.add(host_participant)

            # Optionally 1 peer attendee
            other_peers = [u for u in cput_users if u.id != host.id]
            if other_peers:
                attendee = random.choice(other_peers)
                p = EventParticipant(eventId=event.id, userId=attendee.id)
                session.add(p)

            await session.commit()
            created_count += 1

        print(f"Successfully seeded {created_count} active 2027 events for CPUT!")

if __name__ == "__main__":
    asyncio.run(seed())
