import json
import random
import asyncio
from typing import List, Dict, Any
import google.generativeai as genai
import pusher

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update

from app.core.config import settings
from app.core.limiter import chat_limiter
from app.db.session import async_session
from app.models.message import Message

MODERATION_MODELS = [
    "gemini-3-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash"
]

moderation_queue = asyncio.Queue()

pusher_client = None
if settings.NEXT_PUBLIC_PUSHER_APP_ID:
    pusher_client = pusher.Pusher(
        app_id=settings.NEXT_PUBLIC_PUSHER_APP_ID,
        key=settings.NEXT_PUBLIC_PUSHER_KEY,
        secret=settings.PUSHER_SECRET,
        cluster=settings.NEXT_PUBLIC_PUSHER_CLUSTER,
        ssl=True,
        encryption_master_key_base64=settings.PUSHER_ENCRYPTION_KEY
    )

async def execute_batch_moderation_with_fallback(batch: List[Dict[str, Any]], max_attempts: int = 5) -> List[str]:
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys:
        return []

    prompt = f"""
    Analyze the following batch of chat messages for harassment, hate speech, severe bullying, explicit danger, profanity, or highly abusive language.
    Respond with a JSON array containing the messageIds of ONLY the messages that are FLAGGED. If none are flagged, return an empty array [].
    Output ONLY valid JSON.
    Messages to check:
    {json.dumps(batch)}
    """
    
    total_combinations = len(MODERATION_MODELS) * len(api_keys)
    actual_max_attempts = max(max_attempts, total_combinations)
    attempt_index = random.randint(0, max(0, total_combinations - 1))
    
    async def fetch():
        nonlocal attempt_index
        last_error = None
        for i in range(actual_max_attempts):
            model_index = attempt_index % len(MODERATION_MODELS)
            key_index = (attempt_index // len(MODERATION_MODELS)) % len(api_keys)
            
            model_name = MODERATION_MODELS[model_index]
            api_key = api_keys[key_index]
            identifier = f"{api_key}-{model_name}"
            
            if not chat_limiter.can_request(identifier):
                print(f"Local rate limit hit for {model_name} on key index {key_index}. Trying next...")
                last_error = Exception(f"429 Local limit hit for {model_name}")
                attempt_index = (attempt_index + 1) % total_combinations
                continue
                
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            
            try:
                result = await asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                text = result.text.strip()
                try:
                    clean_text = text.strip()
                    if clean_text.startswith('```'):
                        clean_text = clean_text.strip('`').strip()
                        if clean_text.startswith('json'):
                            clean_text = clean_text[4:].strip()
                    parsed = json.loads(clean_text)
                except Exception:
                    # fallback extraction: find the first and last brackets
                    start = text.find('[')
                    end = text.rfind(']')
                    if start != -1 and end != -1 and end > start:
                        try:
                            parsed = json.loads(text[start:end+1])
                        except Exception:
                            raise Exception(f"Failed to parse JSON array. Content: {text[:100]}...")
                    else:
                        raise Exception(f"Failed to parse JSON. Content: {text[:100]}...")
                
                flagged_ids = []
                if isinstance(parsed, list):
                    flagged_ids = [str(x) for x in parsed]
                elif isinstance(parsed, dict):
                    arrays = [v for v in parsed.values() if isinstance(v, list)]
                    if arrays:
                        flagged_ids = [str(x) for x in arrays[0]]
                return flagged_ids
            except Exception as e:
                print(f"Moderation failed on attempt {i+1} with {MODERATION_MODELS[model_index]}: {e}")
                last_error = e
                
            attempt_index = (attempt_index + 1) % total_combinations
            await asyncio.sleep(0.5)
            
        if last_error and "429" in str(last_error):
            raise last_error
            
        return []
            
    try:
        return await asyncio.wait_for(fetch(), timeout=45.0)
    except asyncio.TimeoutError:
        print("Moderation batch fetch timed out.")
        raise Exception("Timeout")

async def process_moderation_queue():
    while True:
        await asyncio.sleep(5)
        if moderation_queue.empty():
            continue
            
        # We no longer check the global rate limit here,
        # we check per-model and per-key inside fetch() instead.
            
        batch_size = 20
        batch = []
        try:
            for _ in range(batch_size):
                batch.append(moderation_queue.get_nowait())
        except asyncio.QueueEmpty:
            pass
            
        if not batch:
            continue
            
        try:
            flagged_ids = await execute_batch_moderation_with_fallback(batch, max_attempts=5)
            
            if flagged_ids:
                async with async_session() as db:
                    for flagged_id in flagged_ids:
                        item = next((m for m in batch if m["messageId"] == flagged_id), None)
                        if item:
                            print(f"Post-Moderation: Message {item['messageId']} was FLAGGED. Masking.")
                            # Update DB
                            message = await db.get(Message, item["messageId"])
                            if message:
                                message.isFlagged = True
                                db.add(message)
                                await db.commit()
                            
                            # Broadcast to clients
                            if pusher_client:
                                try:
                                    pusher_client.trigger(
                                        f"private-encrypted-{item['eventId']}", 
                                        'message-flagged', 
                                        { 
                                            "messageId": item['messageId'],
                                            "text": "This message has been removed for violating our community guidelines."
                                        }
                                    )
                                except Exception as e:
                                    print("Moderation Pusher Error:", e)
                                    
        except Exception as e:
            if "429" in str(e):
                print("Background Moderation hit 429. Re-queueing batch and backing off.")
                for item in reversed(batch):
                    moderation_queue.put_nowait(item)
                await asyncio.sleep(60)
            elif "Timeout" in str(e):
                print("Background Moderation timed out. Re-queueing batch.")
                for item in reversed(batch):
                    moderation_queue.put_nowait(item)
            else:
                print("Background Moderation batch failed:", e)
