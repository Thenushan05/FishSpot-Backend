"""
Maintenance Rule Calculation Engine

This module contains the core logic to calculate maintenance statuses
based on rules, current vessel state, and maintenance logs.
"""

from typing import List, Optional, Dict, Literal
from datetime import datetime, timedelta
from app.schemas.maintenance import (
    MaintenanceRule,
    VesselState,
    MaintenanceLog,
    PartMaintenanceStatus,
    SystemMaintenanceStatus,
    VesselMaintenanceSummary
)


def calculate_part_status(
    rule: MaintenanceRule,
    vessel_state: VesselState,
    last_log: Optional[MaintenanceLog] = None
) -> PartMaintenanceStatus:
    """
    Calculate maintenance status for a single part based on its rule.
    
    Args:
        rule: The maintenance rule defining when maintenance is due
        vessel_state: Current state of the vessel (engine hours, trips, etc.)
        last_log: Most recent maintenance log for this part (optional)
    
    Returns:
        PartMaintenanceStatus with calculated status and remaining time/trips/hours
    """
    
    trigger_type = rule.trigger_type
    interval = rule.interval_value
    warning = rule.warning_before
    
    # Determine last service value and current value based on trigger type
    if trigger_type == "hours":
        # Ensure numeric values
        try:
            current = int(vessel_state.engine_hours)
        except Exception:
            current = 0
        try:
            last = int(last_log.engine_hours_at_service) if last_log and last_log.engine_hours_at_service is not None else 0
        except Exception:
            last = 0
        unit = "hours"
        
    elif trigger_type == "trips":
        try:
            current = int(vessel_state.total_trips)
        except Exception:
            current = 0
        try:
            last = int(last_log.trips_at_service) if last_log and last_log.trips_at_service is not None else 0
        except Exception:
            last = 0
        unit = "trips"
        
    elif trigger_type == "days":
        # Calculate days since last service
        if last_log and last_log.done_at:
            last_service_date = datetime.fromisoformat(last_log.done_at.replace('Z', '+00:00'))
            current_date = datetime.now()
            days_since_service = (current_date - last_service_date).days
            current = days_since_service
            last = 0  # Always measure from when service was done
        else:
            # No service logged yet - assume it's been a long time
            current = interval + 1  # Force overdue
            last = 0
        unit = "days"
        
    elif trigger_type == "sensor":
        # For future IoT sensor integration
        # For now, return a placeholder status
        return PartMaintenanceStatus(
            name=rule.part_name,
            status="ok",
            trigger_type=trigger_type,
            message="Sensor monitoring active",
            last_service=last_log
        )
    else:
        # Unknown trigger type
        return PartMaintenanceStatus(
            name=rule.part_name,
            status="ok",
            trigger_type=trigger_type,
            message="Unknown trigger type",
            last_service=last_log
        )
    
    # Calculate when maintenance is due
    due_at = last + interval
    remaining = due_at - current
    
    # Determine status
    # Treat remaining < 0 as overdue. If remaining == 0 consider it "due now" (due_soon)
    if remaining < 0:
        status = "overdue"
        message = f"{rule.part_name} is overdue by {abs(remaining)} {unit}"
    elif remaining == 0:
        status = "due_soon"
        message = f"{rule.part_name} is due now"
    elif remaining <= warning:
        status = "due_soon"
        message = f"{rule.part_name} due in {remaining} {unit}"
    else:
        status = "ok"
        message = f"{rule.part_name} due in {remaining} {unit}"
    
    return PartMaintenanceStatus(
        name=rule.part_name,
        status=status,
        trigger_type=trigger_type,
        current_value=current,
        due_at_value=due_at,
        remaining=remaining,
        message=message,
        last_service=last_log
    )


def calculate_system_status(
    system_id: str,
    system_name: str,
    rules: List[MaintenanceRule],
    vessel_state: VesselState,
    logs: Dict[str, MaintenanceLog]  # part_name -> latest log
) -> SystemMaintenanceStatus:
    """
    Calculate maintenance status for an entire system by aggregating all its parts.
    
    Args:
        system_id: ID of the system (e.g., "engine")
        system_name: Display name (e.g., "Main Engine")
        rules: All maintenance rules for this system
        vessel_state: Current vessel state
        logs: Dictionary mapping part_name to most recent maintenance log
    
    Returns:
        SystemMaintenanceStatus with overall system status and all part statuses
    """
    
    part_statuses = []
    
    # Calculate status for each part
    for rule in rules:
        last_log = logs.get(rule.part_name)
        part_status = calculate_part_status(rule, vessel_state, last_log)
        part_statuses.append(part_status)
    
    # Determine overall system status (most critical part determines system status)
    if any(p.status == "overdue" for p in part_statuses):
        system_status = "overdue"
        # Find the most overdue part
        overdue_parts = [p for p in part_statuses if p.status == "overdue"]
        summary = f"{len(overdue_parts)} part(s) overdue"
        
    elif any(p.status == "due_soon" for p in part_statuses):
        system_status = "due_soon"
        # Find the part that's due soonest
        due_soon_parts = [p for p in part_statuses if p.status == "due_soon"]
        if due_soon_parts:
            # Sort by remaining time and pick the most urgent
            most_urgent = min(due_soon_parts, key=lambda p: p.remaining if p.remaining is not None else 999999)
            summary = most_urgent.message
        else:
            summary = f"{len(due_soon_parts)} part(s) due soon"
    else:
        system_status = "operational"
        summary = "All systems operational"
    
    return SystemMaintenanceStatus(
        system_id=system_id,
        system_name=system_name,
        status=system_status,
        parts=part_statuses,
        summary_message=summary
    )


def calculate_vessel_maintenance_summary(
    vessel_id: str,
    vessel_name: str,
    vessel_state: VesselState,
    all_rules: List[MaintenanceRule],
    all_logs: List[MaintenanceLog]
) -> VesselMaintenanceSummary:
    """
    Calculate complete maintenance summary for a vessel.
    
    Args:
        vessel_id: Vessel ID
        vessel_name: Vessel display name
        vessel_state: Current vessel state (engine hours, trips, etc.)
        all_rules: All maintenance rules for this vessel
        all_logs: All maintenance logs for this vessel
    
    Returns:
        VesselMaintenanceSummary with calculated statuses for all systems
    """
    
    # Group rules by system
    rules_by_system: Dict[str, List[MaintenanceRule]] = {}
    for rule in all_rules:
        if rule.system_id not in rules_by_system:
            rules_by_system[rule.system_id] = []
        rules_by_system[rule.system_id].append(rule)
    
    # Group logs by system and part (keep only most recent per part)
    logs_by_system: Dict[str, Dict[str, MaintenanceLog]] = {}
    for log in all_logs:
        if log.system_id not in logs_by_system:
            logs_by_system[log.system_id] = {}
        
        # Keep only the most recent log for each part
        if log.part_name not in logs_by_system[log.system_id]:
            logs_by_system[log.system_id][log.part_name] = log
        else:
            existing_log = logs_by_system[log.system_id][log.part_name]
            # Prefer `created_at` if available because it reliably reflects insertion order/timestamp
            # Fall back to `done_at` if `created_at` is not present. Also consider numeric counters
            # (engine_hours_at_service / trips_at_service) as tiebreakers.
            def parse_dt(val):
                try:
                    if val is None:
                        return None
                    if isinstance(val, str):
                        return datetime.fromisoformat(val.replace('Z', '+00:00'))
                    if isinstance(val, datetime):
                        return val
                except Exception:
                    return None
                return None

            new_created = parse_dt(getattr(log, "created_at", None) or log.created_at if hasattr(log, "created_at") else None)
            existing_created = parse_dt(getattr(existing_log, "created_at", None) or existing_log.created_at if hasattr(existing_log, "created_at") else None)

            if new_created and existing_created:
                if new_created > existing_created:
                    logs_by_system[log.system_id][log.part_name] = log
                    continue
            elif new_created and not existing_created:
                logs_by_system[log.system_id][log.part_name] = log
                continue

            # Fallback to comparing done_at
            new_done = parse_dt(getattr(log, "done_at", None))
            existing_done = parse_dt(getattr(existing_log, "done_at", None))
            if new_done and existing_done:
                if new_done > existing_done:
                    logs_by_system[log.system_id][log.part_name] = log
                    continue

            # As further fallback, compare numeric counters if present
            try:
                new_hours = int(log.engine_hours_at_service) if getattr(log, "engine_hours_at_service", None) is not None else None
            except Exception:
                new_hours = None
            try:
                existing_hours = int(existing_log.engine_hours_at_service) if getattr(existing_log, "engine_hours_at_service", None) is not None else None
            except Exception:
                existing_hours = None
            if new_hours is not None and existing_hours is not None:
                if new_hours > existing_hours:
                    logs_by_system[log.system_id][log.part_name] = log
                    continue

            try:
                new_trips = int(log.trips_at_service) if getattr(log, "trips_at_service", None) is not None else None
            except Exception:
                new_trips = None
            try:
                existing_trips = int(existing_log.trips_at_service) if getattr(existing_log, "trips_at_service", None) is not None else None
            except Exception:
                existing_trips = None
            if new_trips is not None and existing_trips is not None:
                if new_trips > existing_trips:
                    logs_by_system[log.system_id][log.part_name] = log
                    continue
    
    # System name mapping (you can make this configurable)
    system_names = {
        "engine": "Main Engine",
        "nets": "Nets & Gear",
        "safety": "Safety Equipment",
        "electronics": "Electronics",
        "hydraulics": "Hydraulic Systems",
        "cooling": "Cooling System",
        "fuel": "Fuel System"
    }
    
    # Calculate status for each system
    system_statuses = []
    for system_id, rules in rules_by_system.items():
        system_name = system_names.get(system_id, system_id.title())
        logs = logs_by_system.get(system_id, {})
        system_status = calculate_system_status(system_id, system_name, rules, vessel_state, logs)
        system_statuses.append(system_status)
    
    # Determine overall vessel status
    if any(s.status == "overdue" for s in system_statuses):
        overall_status = "overdue"
    elif any(s.status == "due_soon" for s in system_statuses):
        overall_status = "due_soon"
    elif any(s.status == "critical" for s in system_statuses):
        overall_status = "critical"
    elif any(s.status == "offline" for s in system_statuses):
        overall_status = "offline"
    else:
        overall_status = "operational"
    
    return VesselMaintenanceSummary(
        vessel_id=vessel_id,
        vessel_name=vessel_name,
        state=vessel_state,
        systems=system_statuses,
        overall_status=overall_status,
        generated_at=datetime.now()
    )


def update_vessel_state_after_trip(
    vessel_state: VesselState,
    trip_duration_hours: float,
    trip_date: str
) -> VesselState:
    """
    Update vessel state counters after completing a trip.
    
    Args:
        vessel_state: Current vessel state
        trip_duration_hours: How many engine hours this trip took
        trip_date: Date of the trip (ISO string)
    
    Returns:
        Updated VesselState
    """
    vessel_state.engine_hours += int(trip_duration_hours)
    vessel_state.total_trips += 1
    vessel_state.last_trip_date = trip_date
    vessel_state.updated_at = datetime.now()
    return vessel_state
