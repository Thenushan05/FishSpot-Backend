from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Ensure password is within bcrypt's 72-byte limit"""
        password_bytes = v.encode('utf-8')
        if len(password_bytes) > 72:
            # Truncate to 72 bytes safely
            truncated = password_bytes[:72]
            # Decode and re-encode to ensure we don't cut in the middle of a multi-byte character
            v = truncated.decode('utf-8', errors='ignore')
        return v


class RegisterIn(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Ensure password is within bcrypt's 72-byte limit"""
        password_bytes = v.encode('utf-8')
        if len(password_bytes) > 72:
            # Truncate to 72 bytes safely
            truncated = password_bytes[:72]
            # Decode and re-encode to ensure we don't cut in the middle of a multi-byte character
            v = truncated.decode('utf-8', errors='ignore')
        return v
