from pydantic import BaseModel
from typing import Optional, Dict, Any


class AgentQuery(BaseModel):
    text: str
    user_id: Optional[int]


class AgentResponse(BaseModel):
    text: str
    suggested_trip_id: Optional[int]
    metadata: Optional[Dict[str, Any]]
