from pydantic import BaseModel
from typing import Optional
import datetime


class TripBase(BaseModel):
    name: str
    port: Optional[str]


class TripCreate(TripBase):
    start: Optional[datetime.datetime]
    end: Optional[datetime.datetime]


class TripOut(TripBase):
    id: int
    user_id: int

    class Config:
        orm_mode = True
