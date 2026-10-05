from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    gem_score: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class ClaimRequest(BaseModel):
    content: str

class VerificationResponse(BaseModel):
    claim_id: Optional[int] = None
    verdict: str
    explanation: str
    evidence_urls: List[str] = []
