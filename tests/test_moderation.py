import pytest
import asyncio
from unittest.mock import patch, MagicMock
from app.services.moderation import execute_batch_moderation_with_fallback, moderation_queue
from app.core.limiter import chat_limiter
from app.services.llm_service import extract_tags_from_bio

@pytest.mark.asyncio
async def test_tc005_ai_bio_extraction():
    """
    TC-005: AI Bio Extraction
    Submit an onboarding bio containing implicit interests.
    Expected: AI parses and returns tags. (Mocked response)
    """
    mock_result = MagicMock()
    mock_result.text = '["Fitness", "Evening Availability"]'
    
    with patch("asyncio.to_thread", return_value=mock_result), \
         patch("app.services.llm_service.events_limiter.can_request", return_value=True):
        tags = await extract_tags_from_bio("I love lifting weights after class")
        assert tags == ["FITNESS", "EVENING AVAILABILITY"]

@pytest.mark.asyncio
async def test_tc006_ai_moderation_harassment():
    """
    TC-006: AI Moderation (True Positive)
    Send a chat message containing harassment.
    Expected: Mocked Gemini returns FLAGGED.
    """
    batch = [{"messageId": "msg1", "text": "I will hurt you", "eventId": "evt1"}]
    
    mock_result = MagicMock()
    mock_result.text = '["msg1"]'
    
    with patch("asyncio.to_thread", return_value=mock_result), \
         patch("app.services.moderation.settings.GEMINI_API_KEY", "test_key"):
        
        flagged_ids = await execute_batch_moderation_with_fallback(batch)
        assert "msg1" in flagged_ids

@pytest.mark.asyncio
async def test_tc007_ai_moderation_safe():
    """
    TC-007: AI Moderation (True Negative)
    Send a chat message containing casual student slang.
    Expected: Mocked Gemini returns SAFE (empty array).
    """
    batch = [{"messageId": "msg2", "text": "This exam is so f***ing hard", "eventId": "evt1"}]
    
    mock_result = MagicMock()
    mock_result.text = '[]'
    
    with patch("asyncio.to_thread", return_value=mock_result), \
         patch("app.services.moderation.settings.GEMINI_API_KEY", "test_key"):
        
        flagged_ids = await execute_batch_moderation_with_fallback(batch)
        assert len(flagged_ids) == 0

@pytest.mark.asyncio
async def test_tc008_ai_rate_limiter_fallback():
    """
    TC-008: AI Rate Limiter Fallback
    Artificially trigger a 429 Rate Limit error on the primary model.
    Expected: The AILimiter catches the error and cycles to the next model successfully.
    """
    batch = [{"messageId": "msg3", "text": "Hello", "eventId": "evt1"}]
    
    # We will mock the asyncio.to_thread to throw an exception on the first call, 
    # and succeed on the second call.
    call_count = 0
    def mock_to_thread(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("429 Resource has been exhausted")
        else:
            mock_res = MagicMock()
            mock_res.text = '[]'
            return mock_res
            
    with patch("asyncio.to_thread", side_effect=mock_to_thread), \
         patch("app.services.moderation.settings.GEMINI_API_KEY", "test_key"), \
         patch("asyncio.sleep", return_value=None): # skip sleep for fast test
         
        flagged_ids = await execute_batch_moderation_with_fallback(batch, max_attempts=5)
        
        assert len(flagged_ids) == 0
        assert call_count > 1 # Proves it fell back and retried
