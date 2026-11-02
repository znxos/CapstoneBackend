import json
import random
import math
import asyncio
from typing import List, Dict, Any
import google.generativeai as genai
from app.core.config import settings
from app.core.limiter import events_limiter

RECOMMENDATION_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash"
]

def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    if not isinstance(vec_a, (list, tuple)) or not isinstance(vec_b, (list, tuple)):
        return 0.0
    if len(vec_a) != len(vec_b):
        return 0.0
    
    try:
        a_floats = [float(x) for x in vec_a]
        b_floats = [float(x) for x in vec_b]
    except (ValueError, TypeError):
        return 0.0

    dot_product = sum(a * b for a, b in zip(a_floats, b_floats))
    norm_a = math.sqrt(sum(a * a for a in a_floats))
    norm_b = math.sqrt(sum(b * b for b in b_floats))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    return dot_product / (norm_a * norm_b)

async def generate_user_embedding(user_data: Dict[str, Any]) -> List[float]:
    if not events_limiter.can_request():
        print("Events limiter rate limited (user embedding).")
        return []
        
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys:
        return []

    text_to_embed = f"{user_data.get('bio', '')} {' '.join(user_data.get('interests', []))} {' '.join(user_data.get('lookingForTags', []))} {' '.join(user_data.get('extractedAiTags', []))} {' '.join(user_data.get('languages', []))}"
    
    try:
        genai.configure(api_key=random.choice(api_keys))
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text_to_embed,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Failed to generate user embedding: {e}")
        return []

async def generate_event_embedding(event_data: Dict[str, Any]) -> List[float]:
    if not events_limiter.can_request():
        print("Events limiter rate limited (event embedding).")
        return []
        
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys:
        return []

    text_to_embed = f"Title: {event_data.get('title')} Category: {event_data.get('category')} Description: {event_data.get('description')}"
    
    try:
        genai.configure(api_key=random.choice(api_keys))
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text_to_embed,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Failed to generate event embedding: {e}")
        return []

async def rerank_and_rationalize_events(
    user_context: str, 
    events_contexts: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Evaluates candidate events against the user profile using Gemini Flash.
    Returns a dict mapping eventId to {"score": int (10-99), "rationale": str}.
    """
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys or not events_contexts:
        return {}

    events_payload = [
        {
            "id": e["eventId"],
            "eventDetails": e.get("eventContext", ""),
            "baselineSimilarity": e.get("baselineScore", 50)
        }
        for e in events_contexts
    ]
    events_json_str = json.dumps(events_payload)

    prompt = f"""You are an intelligent, empathetic campus event recommender.
Evaluate the compatibility between the following User Profile and each candidate Event.

User Profile:
{user_context}

Candidate Events:
{events_json_str}

Evaluation Criteria:
1. Vibe & Energy Alignment: Factor in the user's social energy level (Low/Medium/High) and introvert/extrovert score (0-100) relative to the event format and host energy.
2. Goal & Interest Synergy: Synthesize the user's bio, interests, and looking-for tags with the event topic and description.
3. Host & Peer Compatibility: Consider common study year, university, languages, and shared background.
4. Score: Assign a calibrated compatibility percentage score from 10 to 99 (e.g. 85-98 for outstanding matches, 60-84 for good matches, <60 for weak matches).
5. Rationale: Write a concise, personalized 1-sentence explanation speaking directly to the user (e.g., "Recommended because your interest in Python and moderate energy level align well with this study group.").

Output Format:
Return STRICTLY a valid JSON object mapping each event ID to an object with "score" (integer 10-99) and "rationale" (string).
Example:
{{
  "event-id-1": {{"score": 92, "rationale": "Recommended because your interest in Python and quiet study vibe align with this group."}},
  "event-id-2": {{"score": 78, "rationale": "Recommended because you and the host attend CPUT and both enjoy weekend outdoor activities."}}
}}

Output ONLY the raw JSON object. Do NOT include markdown code blocks (like ```json), thinking tags, or explanations.
"""

    async def fetch_with_retries():
        total_combinations = len(RECOMMENDATION_MODELS) * len(api_keys)
        attempt_index = random.randint(0, total_combinations - 1)

        for _ in range(total_combinations):
            if not events_limiter.can_request():
                print("Events limiter rate limited (rerank retry loop).")
                break
                
            model_index = attempt_index % len(RECOMMENDATION_MODELS)
            key_index = (attempt_index // len(RECOMMENDATION_MODELS)) % len(api_keys)
            
            genai.configure(api_key=api_keys[key_index])
            model = genai.GenerativeModel(RECOMMENDATION_MODELS[model_index])
            
            try:
                result = await asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                text = result.text.strip()
                raw_json = None
                try:
                    raw_json = json.loads(text)
                except Exception:
                    if "```json" in text:
                        clean_text = text.split("```json")[1].split("```")[0].strip()
                        raw_json = json.loads(clean_text)
                    elif "{" in text and "}" in text:
                        clean_text = text[text.find("{"):text.rfind("}") + 1]
                        raw_json = json.loads(clean_text)

                if isinstance(raw_json, dict):
                    parsed_results = {}
                    for event_id, val in raw_json.items():
                        if isinstance(val, dict):
                            raw_score = val.get("score", 70)
                            try:
                                score = int(raw_score)
                            except Exception:
                                score = 70
                            score = min(max(score, 10), 99)
                            rationale = str(val.get("rationale", "")).strip() or "Recommended based on your profile and interests."
                            parsed_results[event_id] = {"score": score, "rationale": rationale}
                        elif isinstance(val, str):
                            parsed_results[event_id] = {"score": 75, "rationale": val}
                    return parsed_results
            except Exception as e:
                print(f"{RECOMMENDATION_MODELS[model_index]} failed for rerank batch: {e}")
            
            attempt_index = (attempt_index + 1) % total_combinations
            await asyncio.sleep(0.5)
        return {}

    try:
        return await asyncio.wait_for(fetch_with_retries(), timeout=45.0)
    except asyncio.TimeoutError:
        print("Gemini batch reranking timed out after 45s.")
        return {}

async def generate_batch_rationales(user_context: str, events_contexts: List[Dict[str, str]]) -> Dict[str, str]:
    """Backward compatibility wrapper around rerank_and_rationalize_events."""
    rerank_results = await rerank_and_rationalize_events(user_context, events_contexts)
    return {e_id: data.get("rationale", "") for e_id, data in rerank_results.items()}

async def extract_tags_from_bio(bio: str, max_attempts: int = 5) -> List[str]:
    if not bio or len(bio) < 10:
        return []
        
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys:
        print("No valid GEMINI_API_KEY found.")
        return []
        
    prompt = f"""
    Analyze the following user bio and extract up to 5 succinct hobby or interest tags.
    The tags should be single words or short phrases (max 2 words each).
    Format the output as a valid JSON array of strings in all UPPERCASE.
    Do not include markdown blocks or any other text in your response, just the raw JSON array.
    
    Bio: "{bio}"
    """
    
    total_combinations = len(RECOMMENDATION_MODELS) * len(api_keys)
    attempt_index = random.randint(0, max(0, total_combinations - 1))
    
    for i in range(max_attempts):
        if not events_limiter.can_request():
            print("Events limiter rate limited (tag extraction retry loop).")
            break
            
        model_index = attempt_index % len(RECOMMENDATION_MODELS)
        key_index = (attempt_index // len(RECOMMENDATION_MODELS)) % len(api_keys)
        
        try:
            genai.configure(api_key=api_keys[key_index])
            model = genai.GenerativeModel(RECOMMENDATION_MODELS[model_index])
            
            result = await asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            text = result.text.strip()
            
            try:
                tags = json.loads(text)
            except Exception:
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                    tags = json.loads(text)
                else:
                    raise Exception("Failed to parse JSON")
                    
            if isinstance(tags, list):
                return [str(t).upper() for t in tags[:5]]
                
        except Exception as e:
            print(f"[Attempt {i + 1}/{max_attempts}] Model {RECOMMENDATION_MODELS[model_index]} failed: {e}")
            
        attempt_index = (attempt_index + 1) % total_combinations
        await asyncio.sleep(0.5)
        
    print("AI Tag Extraction completely failed after max attempts")
    return []

