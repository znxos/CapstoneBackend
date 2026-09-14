import time
from typing import List

class AILimiter:
    """
    A simple in-memory rate limiter to prevent LLM API quota exhaustion.
    """
    def __init__(self, limit: int, time_window_seconds: int = 60):
        self.limit = limit
        self.time_window_seconds = time_window_seconds
        self.timestamps: List[float] = []
        
    def can_request(self) -> bool:
        now = time.time()
        # Keep only timestamps within the time window
        self.timestamps = [t for t in self.timestamps if now - t < self.time_window_seconds]
        
        if len(self.timestamps) >= self.limit:
            return False
            
        self.timestamps.append(now)
        return True

# Export singleton instances
chat_limiter = AILimiter(limit=5) # 5 requests per minute for chat moderation
events_limiter = AILimiter(limit=5) # 5 requests per minute for recommendations/embeddings
