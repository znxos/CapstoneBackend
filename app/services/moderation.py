import json
import random
import asyncio
import google.generativeai as genai
from app.core.config import settings

async def execute_moderation(text: str) -> bool:
    api_keys = [k.strip() for k in (settings.GEMINI_API_KEY or "").split(",") if k.strip()]
    if not api_keys:
        return False
        
    prompt = f"""
    You are a content moderation system for a university social events app.
    Analyze the following message and return ONLY a JSON object with a single boolean field "flagged".
    Set "flagged" to true if the message contains hate speech, harassment, explicit content, or dangerous activities.
    Set "flagged" to false if it is safe.
    
    Message: "{text}"
    """
    
    async def fetch():
        genai.configure(api_key=random.choice(api_keys))
        model = genai.GenerativeModel("gemini-3-flash")
        
        try:
            result = await asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            data = json.loads(result.text.strip())
            return bool(data.get("flagged", False))
        except Exception as e:
            print(f"Moderation failed: {e}")
            return False
            
    try:
        return await asyncio.wait_for(fetch(), timeout=5.0)
    except asyncio.TimeoutError:
        return False
