from typing import List, Optional
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime

class UserCreate(BaseModel):
    studentEmail: EmailStr
    password: str

    @field_validator('studentEmail')
    @classmethod
    def validate_ac_za(cls, v):
        valid_domains = ["mycput.ac.za", "myuct.ac.za", "myuwc.ac.za", "student.sun.ac.za"]
        domain = str(v).split('@')[-1].lower()
        if domain not in valid_domains:
            raise ValueError('Email must belong to one of the stipulated universities (CPUT, UCT, UWC, SU)')
        return v

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
