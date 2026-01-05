"""
Maintenance Rules API - Dynamic rule-based maintenance tracking

This module provides endpoints for:
- Creating and managing maintenance rules
- Tracking vessel state (engine hours, trips, etc.)
- Logging maintenance activities
- Calculating real-time maintenance status
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime
from bson import ObjectId

from app.schemas.maintenance import (
    MaintenanceRule,
    VesselState,
    MaintenanceLog,
    VesselMaintenanceSummary,
    CreateMaintenanceRuleRequest,
    UpdateMaintenanceRuleRequest,
    UpdateVesselStateRequest,
    LogMaintenanceRequest
)
from app.core.auth import get_current_user
from app.db.mongo import get_db_async
from app.services.maintenance_calculator import (
    calculate_vessel_maintenance_summary,
    update_vessel_state_after_trip
)

router = APIRouter()


# ========== Maintenance Rules Endpoints ==========

@router.get("/rules", response_model=List[MaintenanceRule])
async def get_maintenance_rules(
    system_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all maintenance rules, optionally filtered by system_id.
    Rules are shared across all vessels but can be customized per user.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Build query
    query = {"userId": user_id}
    if system_id:
        query["system_id"] = system_id
    
    rules_cursor = db.maintenance_rules.find(query)
    rules = await rules_cursor.to_list(length=1000)
    
    # Convert ObjectId to string
    for rule in rules:
        rule["id"] = str(rule.pop("_id"))
        rule.pop("userId", None)
    
    return rules


@router.post("/rules", response_model=MaintenanceRule)
async def create_maintenance_rule(
    request: CreateMaintenanceRuleRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new maintenance rule.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    rule_dict = request.dict()
    rule_dict["userId"] = user_id
    rule_dict["created_at"] = datetime.now()
    
    result = await db.maintenance_rules.insert_one(rule_dict)
    rule_dict["id"] = str(result.inserted_id)
    rule_dict.pop("_id", None)
    rule_dict.pop("userId", None)
    
    return rule_dict


@router.put("/rules/{rule_id}", response_model=MaintenanceRule)
async def update_maintenance_rule(
    rule_id: str,
    request: UpdateMaintenanceRuleRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing maintenance rule.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Build update dict (only include provided fields)
    update_dict = {k: v for k, v in request.dict().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await db.maintenance_rules.update_one(
        {"_id": ObjectId(rule_id), "userId": user_id},
        {"$set": update_dict}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Maintenance rule not found")
    
    # Fetch updated rule
    rule = await db.maintenance_rules.find_one({"_id": ObjectId(rule_id)})
    rule["id"] = str(rule.pop("_id"))
    rule.pop("userId", None)
    
    return rule


@router.delete("/rules/{rule_id}")
async def delete_maintenance_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a maintenance rule.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    result = await db.maintenance_rules.delete_one(
        {"_id": ObjectId(rule_id), "userId": user_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Maintenance rule not found")
    
    return {"message": "Rule deleted successfully"}


# ========== Vessel State Endpoints ==========

@router.get("/vessels/{vessel_id}/state", response_model=VesselState)
async def get_vessel_state(
    vessel_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get current state/counters for a vessel.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Verify vessel ownership
    vessel = await db.vessels.find_one({
        "_id": ObjectId(vessel_id),
        "userId": user_id
    })
    
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    # Get vessel state (create default if doesn't exist)
    state = await db.vessel_states.find_one({"vessel_id": vessel_id, "userId": user_id})
    
    if not state:
        # Create default state
        state = {
            "vessel_id": vessel_id,
            "userId": user_id,
            "engine_hours": 0,
            "total_trips": 0,
            "last_trip_date": None,
            "sensor_data": None,
            "updated_at": datetime.now()
        }
        await db.vessel_states.insert_one(state)
    
    state.pop("_id", None)
    return state


@router.patch("/vessels/{vessel_id}/state", response_model=VesselState)
async def update_vessel_state(
    vessel_id: str,
    request: UpdateVesselStateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update vessel state counters.
    Use this after completing a trip or when manually adjusting counters.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Verify vessel ownership
    vessel = await db.vessels.find_one({
        "_id": ObjectId(vessel_id),
        "userId": user_id
    })
    
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    # Build update dict
    update_dict = {k: v for k, v in request.dict().items() if v is not None}
    update_dict["updated_at"] = datetime.now()
    
    # Update or create state
    # Ensure userId is stored with the state so different users don't share state
    update_dict["userId"] = user_id
    result = await db.vessel_states.update_one(
        {"vessel_id": vessel_id, "userId": user_id},
        {"$set": update_dict},
        upsert=True
    )
    
    # Fetch updated state
    state = await db.vessel_states.find_one({"vessel_id": vessel_id, "userId": user_id})
    state.pop("_id", None)
    
    return state


@router.post("/vessels/{vessel_id}/complete-trip")
async def complete_trip(
    vessel_id: str,
    trip_duration_hours: float,
    trip_date: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Update vessel state after completing a trip.
    Automatically increments engine hours and trip count.
    
    Args:
        trip_duration_hours: How many engine hours this trip took
        trip_date: Date of the trip (ISO format)
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Verify vessel ownership
    vessel = await db.vessels.find_one({
        "_id": ObjectId(vessel_id),
        "userId": user_id
    })
    
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    # Get current state (user-scoped)
    state = await db.vessel_states.find_one({"vessel_id": vessel_id, "userId": user_id})
    
    if not state:
        state = {
            "vessel_id": vessel_id,
            "userId": user_id,
            "engine_hours": 0,
            "total_trips": 0,
            "last_trip_date": None,
            "sensor_data": None
        }
    
    # Update counters
    state["engine_hours"] = state.get("engine_hours", 0) + int(trip_duration_hours)
    state["total_trips"] = state.get("total_trips", 0) + 1
    state["last_trip_date"] = trip_date
    state["updated_at"] = datetime.now()
    
    # Save to database
    await db.vessel_states.update_one(
        {"vessel_id": vessel_id, "userId": user_id},
        {"$set": state},
        upsert=True
    )
    
    state.pop("_id", None)
    
    return {
        "message": "Trip completed successfully",
        "state": state
    }


# ========== Maintenance Logs Endpoints ==========

@router.get("/vessels/{vessel_id}/logs", response_model=List[MaintenanceLog])
async def get_maintenance_logs(
    vessel_id: str,
    system_id: Optional[str] = None,
    part_name: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    """
    Get maintenance logs for a vessel, optionally filtered by system and part.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Verify vessel ownership
    vessel = await db.vessels.find_one({
        "_id": ObjectId(vessel_id),
        "userId": user_id
    })
    
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    # Build query
    query = {"vessel_id": vessel_id}
    # Ensure logs returned belong to the requesting user as well (defense-in-depth)
    query["userId"] = user_id
    if system_id:
        query["system_id"] = system_id
    if part_name:
        query["part_name"] = part_name
    
    # Fetch logs sorted by date (most recent first)
    logs_cursor = db.maintenance_logs.find(query).sort("done_at", -1).limit(limit)
    logs = await logs_cursor.to_list(length=limit)
    
    # Convert ObjectId to string
    for log in logs:
        log["id"] = str(log.pop("_id"))
    
    return logs


@router.post("/vessels/{vessel_id}/logs", response_model=MaintenanceLog)
async def log_maintenance(
    vessel_id: str,
    request: LogMaintenanceRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Log that maintenance was performed on a part.
    This resets the maintenance countdown for that part.
    
    If engine_hours_at_service or trips_at_service are not provided,
    they will be auto-filled from the current vessel state.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Verify vessel ownership
    vessel = await db.vessels.find_one({
        "_id": ObjectId(vessel_id),
        "userId": user_id
    })
    
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    # Get current vessel state to auto-fill counters
    state = await db.vessel_states.find_one({"vessel_id": vessel_id, "userId": user_id})
    
    log_dict = request.dict()
    log_dict["vessel_id"] = vessel_id
    # Attach owning user id so logs are clearly owned by a user
    log_dict["userId"] = user_id
    log_dict["created_at"] = datetime.now()
    
    # Auto-fill counters if not provided
    if state:
        if log_dict["engine_hours_at_service"] is None:
            log_dict["engine_hours_at_service"] = state.get("engine_hours", 0)
        if log_dict["trips_at_service"] is None:
            log_dict["trips_at_service"] = state.get("total_trips", 0)
    
    # Coerce numeric counters to ints when possible to ensure DB stores numbers
    try:
        if log_dict.get("engine_hours_at_service") is not None:
            log_dict["engine_hours_at_service"] = int(log_dict["engine_hours_at_service"])
    except Exception:
        # leave as-is if conversion fails
        pass
    try:
        if log_dict.get("trips_at_service") is not None:
            log_dict["trips_at_service"] = int(log_dict["trips_at_service"])
    except Exception:
        pass

    result = await db.maintenance_logs.insert_one(log_dict)
    log_dict["id"] = str(result.inserted_id)
    log_dict.pop("_id", None)

    # After logging maintenance, ensure vessel state counters reflect the
    # recorded service point. If the log reports higher engine hours or trips
    # than the stored vessel state, update the vessel state so the summary
    # calculations use the most recent counters and don't show a just-logged
    # service as still overdue.
    try:
        state = await db.vessel_states.find_one({"vessel_id": vessel_id, "userId": user_id})
        if not state:
            state = {
                "vessel_id": vessel_id,
                "userId": user_id,
                "engine_hours": 0,
                "total_trips": 0,
                "last_trip_date": None,
            }

        updated = False
        # Normalize numeric values
        logged_engine = log_dict.get("engine_hours_at_service")
        logged_trips = log_dict.get("trips_at_service")

        if logged_engine is not None:
            try:
                logged_engine_val = int(logged_engine)
            except Exception:
                logged_engine_val = None
            if logged_engine_val is not None and logged_engine_val > state.get("engine_hours", 0):
                state["engine_hours"] = logged_engine_val
                updated = True

        if logged_trips is not None:
            try:
                logged_trips_val = int(logged_trips)
            except Exception:
                logged_trips_val = None
            if logged_trips_val is not None and logged_trips_val > state.get("total_trips", 0):
                state["total_trips"] = logged_trips_val
                updated = True

        if updated:
            state["updated_at"] = datetime.now()
            # persist updated state
            await db.vessel_states.update_one(
                {"vessel_id": vessel_id, "userId": user_id},
                {"$set": state},
                upsert=True,
            )
    except Exception:
        # Don't fail the log on state update problems; logging should succeed
        pass

    return log_dict


# ========== Maintenance Summary Endpoint (THE MAIN ONE) ==========

@router.get("/vessels/{vessel_id}/summary", response_model=VesselMaintenanceSummary)
async def get_maintenance_summary(
    vessel_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get complete maintenance summary for a vessel.
    
    This calculates the current status of all systems and parts based on:
    - Maintenance rules
    - Current vessel state (engine hours, trips, etc.)
    - Maintenance logs
    
    Returns a comprehensive summary showing what's due, due soon, or overdue.
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Verify vessel ownership and get vessel info
    vessel = await db.vessels.find_one({
        "_id": ObjectId(vessel_id),
        "userId": user_id
    })
    
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")
    
    vessel_name = vessel.get("name", "Unknown Vessel")
    
    # Get vessel state (user-scoped)
    state = await db.vessel_states.find_one({"vessel_id": vessel_id, "userId": user_id})
    
    if not state:
        # Create default state
        state = VesselState(
            vessel_id=vessel_id,
            engine_hours=0,
            total_trips=0,
            last_trip_date=None,
            sensor_data=None,
            updated_at=datetime.now()
        )
    else:
        state.pop("_id", None)
        state = VesselState(**state)
    
    # Get all maintenance rules for this user
    rules_cursor = db.maintenance_rules.find({"userId": user_id})
    rules_list = await rules_cursor.to_list(length=1000)
    
    rules = []
    for rule in rules_list:
        rule["id"] = str(rule.pop("_id"))
        rule.pop("userId", None)
        rules.append(MaintenanceRule(**rule))
    
    # Get all maintenance logs for this vessel (user-scoped)
    logs_cursor = db.maintenance_logs.find({"vessel_id": vessel_id, "userId": user_id})
    logs_list = await logs_cursor.to_list(length=1000)
    
    logs = []
    for log in logs_list:
        log["id"] = str(log.pop("_id"))
        logs.append(MaintenanceLog(**log))
    
    # Calculate summary using the calculation engine
    summary = calculate_vessel_maintenance_summary(
        vessel_id=vessel_id,
        vessel_name=vessel_name,
        vessel_state=state,
        all_rules=rules,
        all_logs=logs
    )
    
    return summary


# ========== Seed Default Rules Endpoint ==========

@router.post("/seed-default-rules")
async def seed_default_rules(
    current_user: dict = Depends(get_current_user)
):
    """
    Create default maintenance rules for a new user.
    This is called once during setup to populate initial rules.
    
    Creates rules for:
    - Engine (oil change, fuel filter)
    - Nets & Gear (net inspection)
    - Safety (lifejacket check)
    - Electronics (battery check)
    """
    db = await get_db_async()
    user_id = str(current_user["user_id"])
    
    # Check if user already has rules
    existing_count = await db.maintenance_rules.count_documents({"userId": user_id})
    
    if existing_count > 0:
        return {
            "message": "User already has maintenance rules",
            "count": existing_count
        }
    
    # Default rules as specified in the requirements
    default_rules = [
        # Engine rules
        {
            "system_id": "engine",
            "part_name": "Engine oil",
            "trigger_type": "hours",
            "interval_value": 100,
            "warning_before": 20,
            "description": "Regular engine oil change",
            "userId": user_id,
            "created_at": datetime.now()
        },
        {
            "system_id": "engine",
            "part_name": "Fuel filter",
            "trigger_type": "hours",
            "interval_value": 300,
            "warning_before": 30,
            "description": "Fuel filter replacement",
            "userId": user_id,
            "created_at": datetime.now()
        },
        # Nets & Gear rules
        {
            "system_id": "nets",
            "part_name": "Net inspection",
            "trigger_type": "trips",
            "interval_value": 3,
            "warning_before": 1,
            "description": "Thorough net inspection for tears and damage",
            "userId": user_id,
            "created_at": datetime.now()
        },
        # Safety rules
        {
            "system_id": "safety",
            "part_name": "Lifejacket check",
            "trigger_type": "days",
            "interval_value": 180,
            "warning_before": 14,
            "description": "Inspect lifejackets for damage and expiration",
            "userId": user_id,
            "created_at": datetime.now()
        },
        # Electronics rules
        {
            "system_id": "electronics",
            "part_name": "Battery check",
            "trigger_type": "days",
            "interval_value": 365,
            "warning_before": 30,
            "description": "Check battery voltage and terminals",
            "userId": user_id,
            "created_at": datetime.now()
        }
    ]
    
    result = await db.maintenance_rules.insert_many(default_rules)
    
    return {
        "message": "Default maintenance rules created successfully",
        "count": len(result.inserted_ids),
        "rules": [
            {
                "system": rule["system_id"],
                "part": rule["part_name"],
                "type": rule["trigger_type"],
                "interval": rule["interval_value"]
            }
            for rule in default_rules
        ]
    }
