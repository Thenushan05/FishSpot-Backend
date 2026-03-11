"""
Favourite fishing spots — per-user CRUD.

POST   /api/v1/spots          – save a spot (name, lat, lng)
GET    /api/v1/spots          – list my spots
DELETE /api/v1/spots/{spot_id} – remove a spot
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.db.mongo import get_database

router = APIRouter()


class SpotIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    total_kg: float = Field(0.0, ge=0, description="Last known catch weight (kg) at this spot")


class SpotOut(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    total_kg: float
    created_at: str


def _fmt(doc: dict) -> SpotOut:
    return SpotOut(
        id=str(doc["_id"]),
        name=doc["name"],
        lat=doc["lat"],
        lng=doc["lng"],
        total_kg=float(doc.get("total_kg", 0.0)),
        created_at=doc.get("created_at", ""),
    )


@router.get("", summary="List my saved spots")
async def list_spots(current_user: dict = Depends(get_current_user)):
    db = get_database()
    cursor = db.spots.find({"user_id": current_user["user_id"]}).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [_fmt(d) for d in docs]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Save a new spot")
async def create_spot(body: SpotIn, current_user: dict = Depends(get_current_user)):
    db = get_database()
    doc = {
        "user_id": current_user["user_id"],
        "name": body.name.strip(),
        "lat": body.lat,
        "lng": body.lng,
        "total_kg": body.total_kg,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.spots.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _fmt(doc)


@router.delete("/{spot_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a spot")
async def delete_spot(spot_id: str, current_user: dict = Depends(get_current_user)):
    db = get_database()
    try:
        oid = ObjectId(spot_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid spot id")
    result = await db.spots.delete_one({"_id": oid, "user_id": current_user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Spot not found")
