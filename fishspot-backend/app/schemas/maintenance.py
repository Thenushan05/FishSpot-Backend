from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ========== NEW: Rules-based Maintenance System ==========

class MaintenanceRule(BaseModel):
    """Rule defining when maintenance should be performed"""
    id: Optional[str] = None  # MongoDB ObjectId as string
    system_id: str  # e.g., "engine", "nets", "safety"
    part_name: str  # e.g., "Engine oil", "Net inspection"
    trigger_type: Literal["hours", "days", "trips", "sensor"]
    interval_value: int  # e.g., 100 hours, 180 days, 3 trips
    warning_before: int  # e.g., warn 20 hours before due
    description: Optional[str] = None
    created_at: Optional[datetime] = None


class VesselState(BaseModel):
    """Current state/counters for a vessel"""
    vessel_id: str
    engine_hours: int = 0  # Total engine hours
    total_trips: int = 0  # Total number of trips
    last_trip_date: Optional[str] = None  # ISO date string
    sensor_data: Optional[Dict[str, Any]] = None  # For future IoT sensors
    updated_at: Optional[datetime] = None


class MaintenanceLog(BaseModel):
    """Log of when maintenance was performed"""
    id: Optional[str] = None  # MongoDB ObjectId as string
    vessel_id: str
    system_id: str
    part_name: str
    done_at: str  # ISO date string
    technician: str
    notes: str
    cost: Optional[str] = None
    # Counters at time of service (to calculate next due date)
    engine_hours_at_service: Optional[int] = None
    trips_at_service: Optional[int] = None
    created_at: Optional[datetime] = None


class PartMaintenanceStatus(BaseModel):
    """Calculated status for a single part"""
    name: str
    status: Literal["ok", "due_soon", "overdue"]
    trigger_type: str  # "hours", "days", "trips", "sensor"
    current_value: Optional[int] = None  # Current hours/trips/days
    due_at_value: Optional[int] = None  # Due at this value
    remaining: Optional[int] = None  # How many hours/trips/days left
    message: Optional[str] = None  # e.g., "Due in 18 hours"
    last_service: Optional[MaintenanceLog] = None


class SystemMaintenanceStatus(BaseModel):
    """Calculated status for a whole system"""
    system_id: str
    system_name: str
    status: Literal["operational", "due_soon", "overdue", "critical", "offline"]
    parts: List[PartMaintenanceStatus]
    summary_message: Optional[str] = None  # e.g., "Engine oil change due soon"


class VesselMaintenanceSummary(BaseModel):
    """Complete maintenance summary for a vessel"""
    vessel_id: str
    vessel_name: str
    state: VesselState
    systems: List[SystemMaintenanceStatus]
    overall_status: Literal["operational", "due_soon", "overdue", "critical", "offline"]
    generated_at: datetime


# ========== Request/Response Models for Rules API ==========

class CreateMaintenanceRuleRequest(BaseModel):
    system_id: str
    part_name: str
    trigger_type: Literal["hours", "days", "trips", "sensor"]
    interval_value: int
    warning_before: int
    description: Optional[str] = None


class UpdateMaintenanceRuleRequest(BaseModel):
    interval_value: Optional[int] = None
    warning_before: Optional[int] = None
    description: Optional[str] = None


class UpdateVesselStateRequest(BaseModel):
    engine_hours: Optional[int] = None
    total_trips: Optional[int] = None
    last_trip_date: Optional[str] = None
    sensor_data: Optional[Dict[str, Any]] = None


class LogMaintenanceRequest(BaseModel):
    system_id: str
    part_name: str
    done_at: str  # ISO date string
    technician: str
    notes: str
    cost: Optional[str] = None
    # These will be auto-filled from current vessel state if not provided
    engine_hours_at_service: Optional[int] = None
    trips_at_service: Optional[int] = None


# ========== Original Models (kept for backward compatibility) ==========

class MaintenanceTask(BaseModel):
    id: str
    task: str
    due: str
    priority: str = Field(..., pattern="^(low|medium|high)$")
    

class ServiceLog(BaseModel):
    date: str
    technician: str
    notes: str
    cost: Optional[str] = None


class SystemSpec(BaseModel):
    value: str
    status: str = Field(default="good", pattern="^(good|warning|critical)$")


class SubPart(BaseModel):
    id: str
    label: str
    x: float
    y: float
    status: str = Field(..., pattern="^(good|warning|critical)$")


class FishingSystem(BaseModel):
    id: str
    name: str
    status: str = Field(..., pattern="^(operational|due-soon|overdue|critical|offline)$")
    description: str
    blueprintImage: str
    specs: Dict[str, Any]  # Can be string or SystemSpec dict
    upcomingTasks: List[MaintenanceTask] = []
    lastService: ServiceLog
    aiTips: Optional[List[str]] = None
    subParts: Optional[List[SubPart]] = None


class VesselStats(BaseModel):
    lastTrip: str
    engineHours: int
    fuelOnBoard: str
    iceCapacity: str
    nextServiceDue: str


class Vessel(BaseModel):
    id: Optional[str] = None
    name: str
    type: str
    stats: VesselStats
    systems: List[FishingSystem]


class VesselListResponse(BaseModel):
    vessels: List[Vessel]


class CreateTaskRequest(BaseModel):
    systemId: str
    task: str
    due: str
    priority: str = Field(..., pattern="^(low|medium|high)$")


class UpdateTaskRequest(BaseModel):
    task: Optional[str] = None
    due: Optional[str] = None
    priority: Optional[str] = None
    completed: Optional[bool] = None


class CreateServiceLogRequest(BaseModel):
    systemId: str
    date: str
    technician: str
    notes: str
    cost: Optional[str] = None


class UpdateSystemStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(operational|due-soon|overdue|critical|offline)$")
