from typing import List, Optional
from pydantic import BaseModel

class UserOnboard(BaseModel):
    displayName: str
    age: int
    university: str
    yearOfStudy: int
    languages: List[str]
    introvertExtrovertScore: int
    socialEnergyLevel: str
    lookingForTags: List[str]
    bio: str
    extractedAiTags: Optional[List[str]] = []
    isInternationalStudent: bool
