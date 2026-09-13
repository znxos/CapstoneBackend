import json
import random
import math
import asyncio
from typing import List, Dict, Any
import google.generativeai as genai
from app.core.config import settings

RECOMMENDATION_MODELS = [
    "gemini-3-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash"
]

def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    return dot_product / (norm_a * norm_b)

async def generate_user_embedding(user_data: Dict[str, Any]) -> List[float]:
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys:
        return []

    text_to_embed = f"{user_data.get('bio', '')} {' '.join(user_data.get('interests', []))} {' '.join(user_data.get('lookingForTags', []))} {' '.join(user_data.get('languages', []))}"
    
    try:
        genai.configure(api_key=random.choice(api_keys))
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text_to_embed,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Failed to generate user embedding: {e}")
        return []

async def generate_event_embedding(event_data: Dict[str, Any]) -> List[float]:
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys:
        return []

    text_to_embed = f"Title: {event_data.get('title')} Category: {event_data.get('category')} Description: {event_data.get('description')}"
    
    try:
        genai.configure(api_key=random.choice(api_keys))
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text_to_embed,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Failed to generate event embedding: {e}")
        return []

async def generate_batch_rationales(user_context: str, events_contexts: List[Dict[str, str]]) -> Dict[str, str]:
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys or not events_contexts:
        return {}

    events_json_str = json.dumps([{"id": e["eventId"], "context": e["eventContext"]} for e in events_contexts])
    
    prompt = f"""
Given the following User Profile and a list of Events, write a 1-sentence personalized rationale for EACH event explaining why they are a good match.
Specifically consider any compatibilities between the User Profile and the [HOST PROFILE] included in the Event Details.
Speak directly to the user (e.g. "Recommended because you and the host both..."). Keep it very concise and natural.

Return the result STRICTLY as a JSON object where the keys are the event IDs and the values are the 1-sentence rationales.
Output ONLY the raw JSON object. Do NOT include any explanations, thinking steps, markdown blocks (like ```json), or extra text.

User Profile: {user_context}
Events: {events_json_str}
"""

    async def fetch_with_retries():
        total_combinations = len(RECOMMENDATION_MODELS) * len(api_keys)
        attempt_index = random.randint(0, total_combinations - 1)

        for _ in range(total_combinations):
            model_index = attempt_index % len(RECOMMENDATION_MODELS)
            key_index = (attempt_index // len(RECOMMENDATION_MODELS)) % len(api_keys)
            
            genai.configure(api_key=api_keys[key_index])
            model = genai.GenerativeModel(RECOMMENDATION_MODELS[model_index])
            
            try:
                # Need to run synchronous generate_content in a thread pool to not block event loop
                result = await asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                text = result.text.strip()
                try:
                    return json.loads(text)
                except Exception:
                    # handle markdown blocks manually if strictly json failed
                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0].strip()
                        return json.loads(text)
            except Exception as e:
                print(f"{RECOMMENDATION_MODELS[model_index]} failed for batch: {e}")
            
            attempt_index = (attempt_index + 1) % total_combinations
            await asyncio.sleep(0.5)
        return {}

    try:
        return await asyncio.wait_for(fetch_with_retries(), timeout=60.0)
    except asyncio.TimeoutError:
        print("Gemini batch rationale generation timed out.")
        return {}
