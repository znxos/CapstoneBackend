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

FIFTY_BLUEPRINTS = [
    # --- TECH (10 Events) ---
    {
        "title": "Cybersecurity & Capture the Flag (CTF) Challenge Jam",
        "category": "Tech",
        "description": "Team-based ethical hacking, cryptography puzzles, and web exploitation challenges. Beginners get guided walk-throughs!",
        "location": "CPUT Bellville IT Building Lab 2.05",
        "capacity": 6,
        "target_uni": "CPUT",
        "days_ahead": 122,
        "duration_hours": 4
    },
    {
        "title": "DevOps, Docker & Cloud Deployment Workshop",
        "category": "Tech",
        "description": "Learn containerization, CI/CD pipelines with GitHub Actions, and deploying full-stack apps to cloud platforms effortlessly.",
        "location": "UCT Leslie Social Sciences Lab 3A",
        "capacity": 8,
        "target_uni": "UCT",
        "days_ahead": 128,
        "duration_hours": 3
    },
    {
        "title": "Competitive Programming & Problem Solving Sprint",
        "category": "Tech",
        "description": "Speed problem solving in C++, Java, and Python. Tackling graph theory, dynamic programming, and greedy algorithms.",
        "location": "Stellenbosch Computer Science Lab 101",
        "capacity": 5,
        "target_uni": "Stellenbosch University",
        "days_ahead": 133,
        "duration_hours": 2
    },
    {
        "title": "Raspberry Pi & Arduino IoT Project Lab",
        "category": "Tech",
        "description": "Hands-on micro-controller tinkering with sensors, LEDs, and wireless telemetry. Breadboards, jumpers, and components supplied.",
        "location": "UWC Physics & Electronics Lab 3",
        "capacity": 4,
        "target_uni": "UWC",
        "days_ahead": 138,
        "duration_hours": 3
    },
    {
        "title": "Frontend UI Showcase: Tailwind & React Animations",
        "category": "Tech",
        "description": "Explore Framer Motion, modern micro-interactions, responsive CSS layouts, and glassmorphism styling in modern web design.",
        "location": "CPUT Design Faculty Computer Centre",
        "capacity": 7,
        "target_uni": "CPUT",
        "days_ahead": 144,
        "duration_hours": 3
    },
    {
        "title": "NLP & Large Language Models Code-Along",
        "category": "Tech",
        "description": "Deep dive into tokenization, transformer attention mechanisms, prompt engineering, and building agentic workflows with APIs.",
        "location": "UCT Upper Campus CS Seminar Room",
        "capacity": 6,
        "target_uni": "UCT",
        "days_ahead": 149,
        "duration_hours": 3
    },
    {
        "title": "Game Physics & Shader Programming in Unity",
        "category": "Tech",
        "description": "Writing custom vertex and fragment HLSL shaders, particle simulations, and 3D rigid body game mechanics.",
        "location": "Stellenbosch Engineering Computer Centre",
        "capacity": 5,
        "target_uni": "Stellenbosch University",
        "days_ahead": 154,
        "duration_hours": 3
    },
    {
        "title": "Blockchain & Web3 Smart Contract Basics",
        "category": "Tech",
        "description": "Understanding decentralized ledgers, EVM, Solidity smart contracts, and decentralized identity concepts in an open discussion.",
        "location": "UWC Innovation Hub Room 2",
        "capacity": 6,
        "target_uni": "UWC",
        "days_ahead": 159,
        "duration_hours": 2
    },
    {
        "title": "Data Analytics & Pandas Kaggle Sprint",
        "category": "Tech",
        "description": "Wrangling messy real-world datasets with Pandas, Seaborn data visualization, and training baseline regression models.",
        "location": "CPUT Commerce Building Lab B",
        "capacity": 8,
        "target_uni": "CPUT",
        "days_ahead": 164,
        "duration_hours": 3
    },
    {
        "title": "Backend Architecture: Redis, WebSockets & Realtime",
        "category": "Tech",
        "description": "Building lightning-fast chat engines and live notifications using Redis pub/sub and WebSocket event broadcasting.",
        "location": "UCT Menzies Engineering Computer Lab",
        "capacity": 7,
        "target_uni": "UCT",
        "days_ahead": 169,
        "duration_hours": 3
    },

    # --- STUDY (10 Events) ---
    {
        "title": "Database Systems & SQL Optimization Study Sprint",
        "category": "Study",
        "description": "Reviewing 3NF normalization, index optimization (B-tree vs Hash), query execution plans, and ACID transaction rules.",
        "location": "CPUT Library Level 3 Discussion Cubicle",
        "capacity": 5,
        "target_uni": "CPUT",
        "days_ahead": 124,
        "duration_hours": 3
    },
    {
        "title": "Operating Systems & Concurrency Review",
        "category": "Study",
        "description": "Mastering virtual memory, process scheduling algorithms, mutex locks, semaphores, and preventing deadlocks.",
        "location": "UCT Oppenheimer Library Study Room 4",
        "capacity": 6,
        "target_uni": "UCT",
        "days_ahead": 129,
        "duration_hours": 3
    },
    {
        "title": "Discrete Math & Probability Exam Prep",
        "category": "Study",
        "description": "Group practice solving combinatorics, mathematical induction proofs, Bayes theorem, and probability distribution problems.",
        "location": "Stellenbosch Science Building Room 204",
        "capacity": 4,
        "target_uni": "Stellenbosch University",
        "days_ahead": 134,
        "duration_hours": 2
    },
    {
        "title": "Biology & Genetics Discussion Circle",
        "category": "Study",
        "description": "Unpacking cellular respiration, CRISPR gene editing mechanisms, Mendelian inheritance, and population genetics.",
        "location": "UWC Life Sciences Building Room 12",
        "capacity": 5,
        "target_uni": "UWC",
        "days_ahead": 139,
        "duration_hours": 3
    },
    {
        "title": "Financial Accounting & Business Stats Group",
        "category": "Study",
        "description": "Working through balance sheets, cash flow statements, cost accounting variance analysis, and statistical hypothesis testing.",
        "location": "CPUT Commerce Faculty Seminar Room",
        "capacity": 6,
        "target_uni": "CPUT",
        "days_ahead": 146,
        "duration_hours": 3
    },
    {
        "title": "Organic Chemistry Reaction Mechanisms Breakdown",
        "category": "Study",
        "description": "Drawing nucleophilic substitution (SN1/SN2), elimination pathways, resonance stabilization, and synthesis trees.",
        "location": "UCT PD Hahn Building Chemistry Study Room",
        "capacity": 4,
        "target_uni": "UCT",
        "days_ahead": 151,
        "duration_hours": 3
    },
    {
        "title": "Constitutional Law & Case Studies Debate",
        "category": "Study",
        "description": "Reviewing South African constitutional precedents, Bill of Rights jurisprudence, and moot court preparation.",
        "location": "UWC Law Faculty Reading Room",
        "capacity": 6,
        "target_uni": "UWC",
        "days_ahead": 156,
        "duration_hours": 2
    },
    {
        "title": "Computer Networks & Protocol Analysis Study",
        "category": "Study",
        "description": "Analyzing OSI 7 layers, TCP 3-way handshakes, DNS propagation, subnetting IP addresses, and Wireshark traces.",
        "location": "CPUT Engineering Quad Study Pod 1",
        "capacity": 5,
        "target_uni": "CPUT",
        "days_ahead": 161,
        "duration_hours": 3
    },
    {
        "title": "Microeconomics & Market Structures Sprint",
        "category": "Study",
        "description": "Tackling perfect competition, monopolies, elasticity models, consumer surplus calculations, and game theory matrices.",
        "location": "Stellenbosch Schumann Building Room 112",
        "capacity": 5,
        "target_uni": "Stellenbosch University",
        "days_ahead": 166,
        "duration_hours": 2
    },
    {
        "title": "Software Engineering Design Patterns Review",
        "category": "Study",
        "description": "Dissecting Singleton, Factory, Observer, Decorator, and Strategy design patterns with clean architecture diagrams.",
        "location": "UCT Snape Building Seminar Room B",
        "capacity": 6,
        "target_uni": "UCT",
        "days_ahead": 172,
        "duration_hours": 2
    },

    # --- OUTDOORS (10 Events) ---
    {
        "title": "Camps Bay Sunset Beach Volleyball",
        "category": "Outdoors",
        "description": "Fun, friendly 4v4 sand volleyball matches as the sun sets over the Atlantic. All skill levels welcome, balls provided!",
        "location": "Camps Bay Beach Volleyball Nets",
        "capacity": 8,
        "target_uni": "UCT",
        "days_ahead": 126,
        "duration_hours": 3
    },
    {
        "title": "Campus 3x3 Basketball Pick-up Games",
        "category": "Outdoors",
        "description": "Fast-paced half-court basketball scrimmages. Great cardio, good vibes, and energetic team play.",
        "location": "CPUT Outdoor Basketball Courts",
        "capacity": 6,
        "target_uni": "CPUT",
        "days_ahead": 131,
        "duration_hours": 2
    },
    {
        "title": "Table Mountain Platteklip Gorge Hike",
        "category": "Outdoors",
        "description": "Climbing Platteklip Gorge to the summit of Table Mountain. Challenging workout with breathtaking panoramic city views.",
        "location": "Table Mountain Lower Cableway Base",
        "capacity": 7,
        "target_uni": "UCT",
        "days_ahead": 136,
        "duration_hours": 4
    },
    {
        "title": "Botanical Garden Sketch & Nature Walk",
        "category": "Outdoors",
        "description": "Relaxing stroll through tropical greenhouse plants and water lily ponds, with time to sketch or sit in quiet contemplation.",
        "location": "Stellenbosch University Botanical Gardens",
        "capacity": 5,
        "target_uni": "Stellenbosch University",
        "days_ahead": 141,
        "duration_hours": 3
    },
    {
        "title": "Sunset Ultimate Frisbee on the Oval",
        "category": "Outdoors",
        "description": "Casual non-contact Ultimate Frisbee games. Learn hammer throws, backhand cutting, and enjoy open grass fields.",
        "location": "UWC Main Sports Oval",
        "capacity": 10,
        "target_uni": "UWC",
        "days_ahead": 147,
        "duration_hours": 2
    },
    {
        "title": "Sea Point Promenade Rollerblade & Sunset Walk",
        "category": "Outdoors",
        "description": "Cruising along the Sea Point oceanfront path from Mouille Point to Bantry Bay. Skate, rollerblade, or walk at your pace.",
        "location": "Sea Point Pavilion Promenade Entrance",
        "capacity": 6,
        "target_uni": "UCT",
        "days_ahead": 152,
        "duration_hours": 2
    },
    {
        "title": "Green Point Park Outdoor Calisthenics & Fitness",
        "category": "Outdoors",
        "description": "Bodyweight circuit training, pull-up bar progressions, and core work outdoors in the beautiful Green Point urban park.",
        "location": "Green Point Outdoor Fitness Zone",
        "capacity": 6,
        "target_uni": "CPUT",
        "days_ahead": 157,
        "duration_hours": 2
    },
    {
        "title": "Newlands Forest Shaded Trail Walk",
        "category": "Outdoors",
        "description": "Peaceful forest loop walk surrounded by pine trees and streams on the slopes of Devils Peak. Ideal study break.",
        "location": "Newlands Forest Picnic Area Parking",
        "capacity": 8,
        "target_uni": "UCT",
        "days_ahead": 162,
        "duration_hours": 3
    },
    {
        "title": "Coastal Cycling Ride & Sea Breeze",
        "category": "Outdoors",
        "description": "Casual weekend bicycle ride along the coastal road. Bring your bike or rent one nearby. Smooth and scenic route.",
        "location": "UWC Sports Club Bicycle Shed",
        "capacity": 5,
        "target_uni": "UWC",
        "days_ahead": 167,
        "duration_hours": 3
    },
    {
        "title": "Outdoor Badminton & Lawn Games",
        "category": "Outdoors",
        "description": "Friendly singles and doubles badminton rallies on the open lawn. Rackets, shuttlecocks, and net setup provided.",
        "location": "Coetzenburg Athletics Ground Lawns",
        "capacity": 8,
        "target_uni": "Stellenbosch University",
        "days_ahead": 173,
        "duration_hours": 2
    },

    # --- SOCIAL (10 Events) ---
    {
        "title": "Campus Karaoke & Lip Sync Battle",
        "category": "Social",
        "description": "Sing your heart out to classic 2000s anthems, pop hits, and Afrobeat jams. Dual mics and zero judgement!",
        "location": "CPUT Student Union Activity Hall",
        "capacity": 10,
        "target_uni": "CPUT",
        "days_ahead": 127,
        "duration_hours": 3
    },
    {
        "title": "Mario Kart & Super Smash Bros Tournament",
        "category": "Social",
        "description": "Double elimination friendly gaming bracket on the big screen projector. Joy-Cons, pro controllers, and snacks ready.",
        "location": "UCT Student Residence Lounge",
        "capacity": 8,
        "target_uni": "UCT",
        "days_ahead": 132,
        "duration_hours": 3
    },
    {
        "title": "Coffee & Multilingual Language Exchange",
        "category": "Social",
        "description": "Practice conversational isiXhosa, Afrikaans, French, or English with peers in an informal coffee shop setting.",
        "location": "Stellenbosch Neelsie Coffee Bar",
        "capacity": 6,
        "target_uni": "Stellenbosch University",
        "days_ahead": 137,
        "duration_hours": 2
    },
    {
        "title": "Film Buffs: Classic Sci-Fi Movie Night",
        "category": "Social",
        "description": "Screening a sci-fi cult classic followed by a lively debate on plot twists, cinematic direction, and special effects.",
        "location": "UWC Student Auditorium Hall B",
        "capacity": 8,
        "target_uni": "UWC",
        "days_ahead": 142,
        "duration_hours": 3
    },
    {
        "title": "Speed Networking: Meet Campus Creators & Coders",
        "category": "Social",
        "description": "5-minute rotational introductions to find project collaborators, hackathon teammates, and fellow ambitious peers.",
        "location": "CPUT Innovation Centre Open Space",
        "capacity": 10,
        "target_uni": "CPUT",
        "days_ahead": 148,
        "duration_hours": 2
    },
    {
        "title": "Anime & Manga Discussion Club",
        "category": "Social",
        "description": "Discuss seasonal anime releases, manga chapters, theory-crafting, and animation styles with fellow passionate fans.",
        "location": "UCT Arts Block Student Lounge",
        "capacity": 7,
        "target_uni": "UCT",
        "days_ahead": 153,
        "duration_hours": 2
    },
    {
        "title": "Late Night Campus Boba Tea & Chill Talk",
        "category": "Social",
        "description": "Grab your favorite milk tea flavor and hang out discussing university life, travel stories, and weekend plans.",
        "location": "Stellenbosch Town Square Boba Shop",
        "capacity": 6,
        "target_uni": "Stellenbosch University",
        "days_ahead": 158,
        "duration_hours": 2
    },
    {
        "title": "Chess & Strategic Board Games Afternoon",
        "category": "Social",
        "description": "Rapid blitz and classical chess matches, plus Risk and Hive. Open to grandmasters and newcomers alike.",
        "location": "UWC Library Courtyard Tables",
        "capacity": 6,
        "target_uni": "UWC",
        "days_ahead": 163,
        "duration_hours": 3
    },
    {
        "title": "Open Deck DJ & Electronic Music Share",
        "category": "Social",
        "description": "Share your favorite music tracks, try your hand at Pioneer CDJs / controllers, and talk music production tips.",
        "location": "CPUT Radio Studio Room 1",
        "capacity": 5,
        "target_uni": "CPUT",
        "days_ahead": 168,
        "duration_hours": 2
    },
    {
        "title": "Campus Cooking & International Potluck Supper",
        "category": "Social",
        "description": "Bring a home-style dish or snack representing your hometown cuisine. Share delicious food and make great friends.",
        "location": "UCT Residence Dining & Kitchen Hall",
        "capacity": 8,
        "target_uni": "UCT",
        "days_ahead": 174,
        "duration_hours": 3
    },

    # --- CREATIVE (10 Events) ---
    {
        "title": "Watercolor & Acrylic Canvas Painting Jam",
        "category": "Creative",
        "description": "Express your imagination with acrylics and watercolor washes. Easels, palettes, and brushes provided for everyone.",
        "location": "Stellenbosch Fine Arts Studio 4",
        "capacity": 6,
        "target_uni": "Stellenbosch University",
        "days_ahead": 123,
        "duration_hours": 3
    },
    {
        "title": "3D Modeling & Blender Animation Circle",
        "category": "Creative",
        "description": "Polygonal modeling, UV unwrapping, procedural texturing, and rendering cute characters using Blender 4.",
        "location": "CPUT Multimedia Lab 2",
        "capacity": 5,
        "target_uni": "CPUT",
        "days_ahead": 135,
        "duration_hours": 3
    },
    {
        "title": "Songwriting & Lyric Collaboration Session",
        "category": "Creative",
        "description": "Co-writing chord progressions, hooks, and lyrical narratives. Bring an acoustic instrument or your notebook.",
        "location": "UCT South African College of Music Room 10",
        "capacity": 4,
        "target_uni": "UCT",
        "days_ahead": 143,
        "duration_hours": 2
    },
    {
        "title": "Analog Film Photography: Darkroom Developing",
        "category": "Creative",
        "description": "Learn 35mm black-and-white negative chemical developing and enlarger print exposures in a traditional darkroom.",
        "location": "UWC Media Centre Darkroom",
        "capacity": 4,
        "target_uni": "UWC",
        "days_ahead": 145,
        "duration_hours": 3
    },
    {
        "title": "Indie Zine Making & Print Collaging",
        "category": "Creative",
        "description": "Folding miniature booklets, cut-and-paste collage typography, photocopier art, and DIY underground publishing.",
        "location": "CPUT Graphic Design Studio 1",
        "capacity": 6,
        "target_uni": "CPUT",
        "days_ahead": 150,
        "duration_hours": 3
    },
    {
        "title": "Clay Sculpting & Ceramic Mug Making",
        "category": "Creative",
        "description": "Pinch pot and slab-building clay pottery techniques. Sculpt a personalized ceramic mug or trinket dish.",
        "location": "Stellenbosch Pottery Studio Workshop",
        "capacity": 5,
        "target_uni": "Stellenbosch University",
        "days_ahead": 155,
        "duration_hours": 3
    },
    {
        "title": "Podcast Hosting & Audio Production Workshop",
        "category": "Creative",
        "description": "Mic technique, Audacity audio cleaning, intro music mixing, and interview formatting for student podcast creators.",
        "location": "UCT Centre for Film & Media Lab",
        "capacity": 4,
        "target_uni": "UCT",
        "days_ahead": 160,
        "duration_hours": 2
    },
    {
        "title": "Logo & Brand Identity Critique Circle",
        "category": "Creative",
        "description": "Bring your logo drafts, portfolio case studies, or branding concepts for constructive peer feedback and typography tips.",
        "location": "UWC Design Lab Room 3",
        "capacity": 6,
        "target_uni": "UWC",
        "days_ahead": 165,
        "duration_hours": 2
    },
    {
        "title": "Creative Storyboarding & Concept Art Jam",
        "category": "Creative",
        "description": "Drafting thumbnail storyboard sequences, cinematic perspective shots, and concept silhouettes on graphic tablets.",
        "location": "CPUT Digital Arts Centre Studio B",
        "capacity": 5,
        "target_uni": "CPUT",
        "days_ahead": 171,
        "duration_hours": 3
    },
    {
        "title": "Improv Acting & Comedy Theatre Games",
        "category": "Creative",
        "description": "'Yes, and...' spontaneity games, character roleplay, and confidence-building improvisational theater exercises.",
        "location": "UCT Little Theatre Rehearsal Space",
        "capacity": 8,
        "target_uni": "UCT",
        "days_ahead": 176,
        "duration_hours": 2
    }
]

async def seed_50_more():
    async with async_session() as session:
        res = await session.execute(select(User))
        all_users = res.scalars().all()
        print(f"Loaded {len(all_users)} existing users from database.")
        
        users_by_uni = {}
        for u in all_users:
            uni = u.university or "CPUT"
            users_by_uni.setdefault(uni, []).append(u)

        created_count = 0
        now = datetime.now(timezone.utc)

        for idx, bp in enumerate(FIFTY_BLUEPRINTS, 1):
            uni = bp["target_uni"]
            eligible_hosts = users_by_uni.get(uni) or all_users
            host = random.choice(eligible_hosts)
            
            # Start date in 2027
            start_time = now + timedelta(days=bp["days_ahead"], hours=random.choice([10, 14, 16, 18]))
            start_time = start_time.replace(minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(hours=bp["duration_hours"])

            # Verify restrictions
            cap = bp["capacity"]
            assert 3 <= cap <= 10, f"Capacity {cap} must be 3-10"
            assert start_time < end_time, "Start must be before end"
            assert end_time > now, "End must be in the future"

            print(f"[{idx}/50] Generating embedding: '{bp['title']}' ({bp['category']})...")
            vector = []
            try:
                vector = await generate_event_embedding({
                    "title": bp["title"],
                    "category": bp["category"],
                    "description": bp["description"]
                })
                # Brief sleep to be courteous to Gemini API rate limits
                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"Embedding notice: {e}, continuing...")

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

            # Optionally 1-2 peers from the same university join
            peers = [u for u in eligible_hosts if u.id != host.id]
            num_attendees = min(random.randint(1, 2), cap - 1)
            if peers and num_attendees > 0:
                attendees = random.sample(peers, min(num_attendees, len(peers)))
                for a in attendees:
                    p = EventParticipant(eventId=event.id, userId=a.id)
                    session.add(p)

            await session.commit()
            created_count += 1
            print(f"  -> Created #{created_count}: '{event.title}' in 2027 hosted by {host.displayName or host.studentEmail} ({uni})")

        print(f"\nSuccessfully seeded all {created_count} future 2027 events!")

if __name__ == "__main__":
    asyncio.run(seed_50_more())
