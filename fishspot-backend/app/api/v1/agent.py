from fastapi import APIRouter, Depends

from app.schemas.agent import AgentQuery, AgentResponse
from app.core.auth import get_current_user
from app.services.agent_service import AgentService

router = APIRouter()


@router.post("/query", response_model=AgentResponse)
def query_agent(query: AgentQuery, user=Depends(get_current_user)):
    """Endpoint that accepts a natural language query and returns structured reply."""
    service = AgentService()
    resp = service.handle_query(query.text, user.get("user_id"))
    return resp
