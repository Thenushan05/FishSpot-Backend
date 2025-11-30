from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from bson import ObjectId

from app.schemas.maintenance import (
    Vessel, VesselListResponse, FishingSystem, MaintenanceTask,
    CreateTaskRequest, UpdateTaskRequest, CreateServiceLogRequest,
    UpdateSystemStatusRequest, ServiceLog
)
from app.core.auth import get_current_user
from app.db.mongo import get_db_async

router = APIRouter()


@router.get("/vessels", response_model=VesselListResponse)
async def get_vessels(current_user: dict = Depends(get_current_user)):
    """
    Get all vessels for the current user.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Fetch vessels owned by this user
    vessels_cursor = db.vessels.find({"userId": user_id})
    vessels = await vessels_cursor.to_list(length=100)
    
    # Convert ObjectId to string
    for vessel in vessels:
        vessel["_id"] = str(vessel["_id"])
        vessel["id"] = vessel.pop("_id")
        # Remove userId from response
        vessel.pop("userId", None)
    
    return {"vessels": vessels}


@router.get("/vessels/{vessel_id}", response_model=Vessel)
async def get_vessel(vessel_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get a specific vessel by ID.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    try:
        vessel = await db.vessels.find_one({
            "_id": ObjectId(vessel_id),
            "userId": user_id
        })
    except:
        raise HTTPException(status_code=400, detail="Invalid vessel ID format")
    
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    vessel["id"] = str(vessel.pop("_id"))
    vessel.pop("userId", None)
    
    return vessel


@router.post("/vessels")
async def create_vessel(vessel: Vessel, current_user: dict = Depends(get_current_user)):
    """
    Create a new vessel.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    vessel_dict = vessel.dict()
    vessel_dict["userId"] = user_id
    vessel_dict.pop("id", None)  # Remove id if present
    
    result = await db.vessels.insert_one(vessel_dict)
    
    return {
        "id": str(result.inserted_id),
        "message": "Vessel created successfully"
    }


@router.put("/vessels/{vessel_id}")
async def update_vessel(
    vessel_id: str,
    vessel: Vessel,
    current_user: dict = Depends(get_current_user)
):
    """
    Update a vessel.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    try:
        vessel_dict = vessel.dict()
        vessel_dict.pop("id", None)
        
        result = await db.vessels.update_one(
            {"_id": ObjectId(vessel_id), "userId": user_id},
            {"$set": vessel_dict}
        )
    except:
        raise HTTPException(status_code=400, detail="Invalid vessel ID format")
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    return {"message": "Vessel updated successfully"}


@router.delete("/vessels/{vessel_id}")
async def delete_vessel(vessel_id: str, current_user: dict = Depends(get_current_user)):
    """
    Delete a vessel.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    try:
        result = await db.vessels.delete_one({
            "_id": ObjectId(vessel_id),
            "userId": user_id
        })
    except:
        raise HTTPException(status_code=400, detail="Invalid vessel ID format")
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    return {"message": "Vessel deleted successfully"}


# System-specific endpoints
@router.patch("/vessels/{vessel_id}/systems/{system_id}/status")
async def update_system_status(
    vessel_id: str,
    system_id: str,
    request: UpdateSystemStatusRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update the status of a specific system.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    try:
        result = await db.vessels.update_one(
            {
                "_id": ObjectId(vessel_id),
                "userId": user_id,
                "systems.id": system_id
            },
            {"$set": {"systems.$.status": request.status}}
        )
    except:
        raise HTTPException(status_code=400, detail="Invalid vessel ID format")
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vessel or system not found")
    
    return {"message": "System status updated successfully"}


# Task management endpoints
@router.post("/vessels/{vessel_id}/systems/{system_id}/tasks")
async def create_task(
    vessel_id: str,
    system_id: str,
    request: CreateTaskRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new maintenance task for a system.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    task = {
        "id": str(ObjectId()),
        "task": request.task,
        "due": request.due,
        "priority": request.priority
    }
    
    try:
        result = await db.vessels.update_one(
            {
                "_id": ObjectId(vessel_id),
                "userId": user_id,
                "systems.id": system_id
            },
            {"$push": {"systems.$.upcomingTasks": task}}
        )
    except:
        raise HTTPException(status_code=400, detail="Invalid vessel ID format")
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vessel or system not found")
    
    return {
        "id": task["id"],
        "message": "Task created successfully"
    }


@router.patch("/vessels/{vessel_id}/systems/{system_id}/tasks/{task_id}")
async def update_task(
    vessel_id: str,
    system_id: str,
    task_id: str,
    request: UpdateTaskRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update a maintenance task.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    update_fields = {}
    if request.task is not None:
        update_fields["systems.$[sys].upcomingTasks.$[task].task"] = request.task
    if request.due is not None:
        update_fields["systems.$[sys].upcomingTasks.$[task].due"] = request.due
    if request.priority is not None:
        update_fields["systems.$[sys].upcomingTasks.$[task].priority"] = request.priority
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    try:
        result = await db.vessels.update_one(
            {"_id": ObjectId(vessel_id), "userId": user_id},
            {"$set": update_fields},
            array_filters=[
                {"sys.id": system_id},
                {"task.id": task_id}
            ]
        )
    except:
        raise HTTPException(status_code=400, detail="Invalid vessel ID format")
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vessel, system, or task not found")
    
    return {"message": "Task updated successfully"}


@router.delete("/vessels/{vessel_id}/systems/{system_id}/tasks/{task_id}")
async def delete_task(
    vessel_id: str,
    system_id: str,
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a maintenance task.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    try:
        result = await db.vessels.update_one(
            {
                "_id": ObjectId(vessel_id),
                "userId": user_id,
                "systems.id": system_id
            },
            {"$pull": {"systems.$.upcomingTasks": {"id": task_id}}}
        )
    except:
        raise HTTPException(status_code=400, detail="Invalid vessel ID format")
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vessel or system not found")
    
    return {"message": "Task deleted successfully"}


# Service log endpoints
@router.post("/vessels/{vessel_id}/systems/{system_id}/service-logs")
async def create_service_log(
    vessel_id: str,
    system_id: str,
    request: CreateServiceLogRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Add a service log entry for a system.
    """
    db = await get_db_async()
    user_id = current_user["user_id"]
    
    service_log = {
        "date": request.date,
        "technician": request.technician,
        "notes": request.notes,
        "cost": request.cost
    }
    
    try:
        result = await db.vessels.update_one(
            {
                "_id": ObjectId(vessel_id),
                "userId": user_id,
                "systems.id": system_id
            },
            {"$set": {"systems.$.lastService": service_log}}
        )
    except:
        raise HTTPException(status_code=400, detail="Invalid vessel ID format")
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Vessel or system not found")
    
    return {"message": "Service log added successfully"}
