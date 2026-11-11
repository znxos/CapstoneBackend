import time
from typing import Dict, List

class AILimiter:
    """
    An in-memory rate limiter to prevent the system from hitting the API quota.
    """
    def __init__(self, limit: int, time_window_seconds: int = 60):
        self.limit = limit
        self.time_window_seconds = time_window_seconds
        self.timestamps: Dict[str, List[float]] = {}
        
    def can_request(self, identifier: str = "default") -> bool:
        now = time.time()
        if identifier not in self.timestamps:
            self.timestamps[identifier] = []
            
        # Keep only timestamps within the time window
        self.timestamps[identifier] = [t for t in self.timestamps[identifier] if now - t < self.time_window_seconds]
        
        if len(self.timestamps[identifier]) >= self.limit:
            return False
            
        self.timestamps[identifier].append(now)
        return True

# Export singleton instances
chat_limiter = AILimiter(limit=5) # 5 requests per minute for chat moderation
events_limiter = AILimiter(limit=5) # 5 requests per minute for recommendations/embeddings
