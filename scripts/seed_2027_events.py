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

EVENT_BLUEPRINTS = [
    # Tech
    {
        "title": "Full-Stack Next.js & Python FastAPI Workshop",
        "category": "Tech",
        "description": "Collaborative hands-on workshop building a live full-stack app with Next.js Turbopack and FastAPI. Beginners and experienced coders welcome!",
        "location": "CPUT Bellville IT Building Lab 1.04",
        "capacity": 8,
        "target_uni": "CPUT",
        "days_ahead": 120, # March 2027
        "duration_hours": 3
    },
    {
        "title": "Machine Learning & AI Prompting Hackathon",
        "category": "Tech",
        "description": "A 4-hour hack sprint experimenting with Gemini LLMs, vector embeddings, and real-time agents. Bring your laptop and creative ideas!",
        "location": "UCT Upper Campus Computer Lab 3",
        "capacity": 6,
        "target_uni": "UCT",
        "days_ahead": 125,
        "duration_hours": 4
    },
    {
        "title": "Open Source Game Dev Sprint (Godot & Rust)",
        "category": "Tech",
        "description": "Building retro 2D games and physics experiments using Godot 4 and Rust. Team up to prototype a mini-game in an afternoon.",
        "location": "Stellenbosch Engineering Computer Centre",
        "capacity": 5,
        "target_uni": "Stellenbosch University",
        "days_ahead": 130,
        "duration_hours": 3
    },
    {
        "title": "Mobile App & Flutter Collaboration",
        "category": "Tech",
        "description": "Brainstorming and building cross-platform student utility apps in Flutter. Great for sharpening your mobile design and Dart skills.",
        "location": "UWC Science Building Lab C",
        "capacity": 6,
        "target_uni": "UWC",
        "days_ahead": 135,
        "duration_hours": 3
    },

    # Study
    {
        "title": "Calculus & Linear Algebra Midterm Prep",
        "category": "Study",
        "description": "Intensive problem-solving session covering multivariable calculus, matrix transformations, and past exam questions in a supportive group.",
        "location": "CPUT Library Group Study Room 4",
        "capacity": 5,
        "target_uni": "CPUT",
        "days_ahead": 140,
        "duration_hours": 3
    },
    {
        "title": "Data Structures & Algorithms Problem Solving",
        "category": "Study",
        "description": "Practicing LeetCode and technical interview problems together: graphs, dynamic programming, and binary search strategies.",
        "location": "UCT Chancellor Oppenheimer Library Room B",
        "capacity": 6,
        "target_uni": "UCT",
        "days_ahead": 145,
        "duration_hours": 2
    },
    {
        "title": "Quiet Focus & Pomodoro Coding Sprint",
        "category": "Study",
        "description": "Structured 25-minute quiet focus intervals with 5-minute break chats. Perfect for finishing assignments or coursework without distractions.",
        "location": "Stellenbosch JS Gericke Library Discussion Room",
        "capacity": 5,
        "target_uni": "Stellenbosch University",
        "days_ahead": 150,
        "duration_hours": 4
    },
    {
        "title": "Physics & Chemistry Exam Revision Circle",
        "category": "Study",
        "description": "Reviewing core principles of thermodynamics, organic mechanisms, and formula derivations before exam week.",
        "location": "UWC Library 2nd Floor Study Cubicles",
        "capacity": 4,
        "target_uni": "UWC",
        "days_ahead": 155,
        "duration_hours": 3
    },

    # Outdoors
    {
        "title": "Lions Head Morning Sunrise Hike",
        "category": "Outdoors",
        "description": "Early morning hike up Lions Head to catch the Atlantic sunrise. Bring water, sturdy footwear, and a camera for epic views.",
        "location": "Lions Head Parking Base, Cape Town",
        "capacity": 8,
        "target_uni": "UCT",
        "days_ahead": 160,
        "duration_hours": 3
    },
    {
        "title": "Campus Soccer & 5-a-Side Friendly Scrimmage",
        "category": "Outdoors",
        "description": "Casual 5v5 soccer scrimmage for fitness and fun. All skill levels welcome. Bibs and balls provided!",
        "location": "CPUT Sports Grounds & Astro Field",
        "capacity": 10,
        "target_uni": "CPUT",
        "days_ahead": 165,
        "duration_hours": 2
    },
    {
        "title": "Kirstenbosch Botanical Gardens Relax & Walk",
        "category": "Outdoors",
        "description": "Scenic stroll along the Boomslang Canopy Walkway followed by light picnic study on the lawns. Great way to recharge outdoors.",
        "location": "Kirstenbosch Main Gate & Tea Room",
        "capacity": 7,
        "target_uni": "UCT",
        "days_ahead": 170,
        "duration_hours": 3
    },
    {
        "title": "Jonkershoek Nature Reserve Trail Walk",
        "category": "Outdoors",
        "description": "Refreshing afternoon walk through the Jonkershoek valley trails. Beautiful mountain landscapes and fresh air.",
        "location": "Jonkershoek Reserve Entrance Gate",
        "capacity": 6,
        "target_uni": "Stellenbosch University",
        "days_ahead": 175,
        "duration_hours": 4
    },

    # Social
    {
        "title": "Friday Board Games & Pizza Night",
        "category": "Social",
        "description": "Unwind after classes with Catan, Secret Hitler, Uno, and collaborative party games. Pizza and soft drinks included!",
        "location": "CPUT Student Centre Lounge 2",
        "capacity": 8,
        "target_uni": "CPUT",
        "days_ahead": 180,
        "duration_hours": 3
    },
    {
        "title": "International Students Meet & Coffee Hangout",
        "category": "Social",
        "description": "Connect with local and international students, share cultural experiences, and practice languages over great coffee.",
        "location": "UCT Food Court & Terrace",
        "capacity": 10,
        "target_uni": "UCT",
        "days_ahead": 185,
        "duration_hours": 2
    },
    {
        "title": "Acoustic Jam Session & Open Mic",
        "category": "Social",
        "description": "Bring your guitar, ukulele, or vocal energy! An informal, relaxed musical jam for lovers of indie, folk, and pop tunes.",
        "location": "Stellenbosch Neelsie Student Centre Piazza",
        "capacity": 6,
        "target_uni": "Stellenbosch University",
        "days_ahead": 190,
        "duration_hours": 2
    },
    {
        "title": "Trivia Night: Pop Culture & University Quiz",
        "category": "Social",
        "description": "Test your knowledge on movies, music, gaming, and campus history. Form teams and compete for fun bragging rights and prizes.",
        "location": "UWC Student Union Courtyard",
        "capacity": 8,
        "target_uni": "UWC",
        "days_ahead": 195,
        "duration_hours": 3
    },

    # Creative
    {
        "title": "Digital Art & UI/UX Design Jam (Figma)",
        "category": "Creative",
        "description": "Designing sleek modern web and mobile interfaces together in Figma. Learn design systems, typography pairing, and micro-interactions.",
        "location": "CPUT Design Faculty Studio 3",
        "capacity": 6,
        "target_uni": "CPUT",
        "days_ahead": 200,
        "duration_hours": 3
    },
    {
        "title": "Photography Campus Photowalk & Editing",
        "category": "Creative",
        "description": "Exploring architectural light, candid portraits, and composition around historic campus landmarks. Mobile cameras or DSLRs welcome.",
        "location": "UCT Memorial Hall Steps & Jameson Plaza",
        "capacity": 5,
        "target_uni": "UCT",
        "days_ahead": 205,
        "duration_hours": 2
    },
    {
        "title": "Creative Writing & Poetry Workshop",
        "category": "Creative",
        "description": "Sharing short stories, personal essays, and poetry with friendly peers. Includes constructive feedback and writing prompts.",
        "location": "Stellenbosch Arts Building Seminar Room 102",
        "capacity": 5,
        "target_uni": "Stellenbosch University",
        "days_ahead": 210,
        "duration_hours": 2
    },
    {
        "title": "Short Film & Video Editing Collab",
        "category": "Creative",
        "description": "Hands-on collaboration covering lighting, DaVinci Resolve color grading, and storytelling for YouTube/TikTok creators.",
        "location": "UWC Media Studies Studio",
        "capacity": 4,
        "target_uni": "UWC",
        "days_ahead": 215,
        "duration_hours": 3
    }
]

async def seed_2027_events():
    async with async_session() as session:
        # Load all existing users
        res = await session.execute(select(User))
        all_users = res.scalars().all()
        print(f"Loaded {len(all_users)} existing users from database.")
        
        # Group users by university
        users_by_uni = {}
        for u in all_users:
            uni = u.university or "CPUT"
            users_by_uni.setdefault(uni, []).append(u)

        created_count = 0
        now = datetime.now(timezone.utc)

        for bp in EVENT_BLUEPRINTS:
            uni = bp["target_uni"]
            eligible_hosts = users_by_uni.get(uni) or all_users
            host = random.choice(eligible_hosts)
            
            # Start date in 2027 (now is late 2026, so days_ahead puts it in 2027)
            start_time = now + timedelta(days=bp["days_ahead"], hours=random.choice([10, 14, 16, 18]))
            # Round to clean minutes
            start_time = start_time.replace(minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(hours=bp["duration_hours"])

            # Enforce restrictions
            cap = bp["capacity"]
            assert 3 <= cap <= 10, f"Capacity {cap} must be 3-10"
            assert start_time < end_time, "Start must be before end"
            assert end_time > now, "End must be in the future"

            print(f"Generating embedding for: {bp['title']} ({bp['category']})...")
            try:
                vector = await generate_event_embedding({
                    "title": bp["title"],
                    "category": bp["category"],
                    "description": bp["description"]
                })
            except Exception as e:
                print(f"Error generating embedding: {e}, using dummy vector")
                vector = [0.0] * 768

            event = Event(
                title=bp["title"],
                category=bp["category"],
                description=bp["description"],
                startTime=start_time,
                endTime=end_time,
                location=bp["location"],
                maxParticipants=cap,
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

            # Optionally have 1-2 peers from same uni join without exceeding capacity
            peers = [u for u in eligible_hosts if u.id != host.id]
            num_attendees = min(random.randint(1, 2), cap - 1)
            if peers and num_attendees > 0:
                attendees = random.sample(peers, min(num_attendees, len(peers)))
                for a in attendees:
                    p = EventParticipant(eventId=event.id, userId=a.id)
                    session.add(p)

            await session.commit()
            created_count += 1
            print(f"Created event #{created_count}: '{event.title}' in 2027 hosted by {host.displayName or host.studentEmail} ({uni})")

        print(f"\nSuccessfully seeded {created_count} future 2027 events!")

if __name__ == "__main__":
    asyncio.run(seed_2027_events())
