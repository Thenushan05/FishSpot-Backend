"""Agent orchestration service that uses other services to answer queries."""
from typing import Optional, Dict, Any

from app.schemas.agent import AgentResponse
from app.services.hotspot_service import HotspotService


class AgentService:
    def __init__(self):
        self.hotspot = HotspotService()

    def handle_query(self, text: str, user_id: Optional[int] = None) -> AgentResponse:
        """Very small rule-based handler: if user asks 'predict' call hotspot service."""
        text_l = text.lower()
        if "predict" in text_l or "hotspot" in text_l:
            # For scaffold, create a simple feature payload
            features = [{"lat": -33.0, "lon": 151.0}]
            preds = self.hotspot.predict(features)
            reply = f"I found {len(preds)} potential hotspot(s). Top score: {preds[0].get('score')}."
            return AgentResponse(text=reply, suggested_trip_id=None, metadata={"predictions": preds})

        # Default fallback
        return AgentResponse(text="I can help with hotspots, trips, and dashboard stats.", suggested_trip_id=None, metadata={})
