from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime

class UserCreate(BaseModel):
    studentEmail: EmailStr
    password: str

class UserLogin(BaseModel):
    studentEmail: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    studentEmail: str
    displayName: Optional[str]
    isVerified: bool
    age: Optional[int]
    university: Optional[str]
    yearOfStudy: Optional[int]
    isFirstTimeUni: Optional[bool]
    isInternationalStudent: Optional[bool]
    isFirstLogin: bool
    bio: Optional[str]
    introvertExtrovertScore: Optional[int] = None
    socialEnergyLevel: Optional[str] = None
    interests: Optional[List[str]] = []
    languages: Optional[List[str]] = []
    lookingForTags: Optional[List[str]] = []
    extractedAiTags: Optional[List[str]] = []
    createdAt: datetime

class Token(BaseModel):
    access_token: str
    token_type: str
