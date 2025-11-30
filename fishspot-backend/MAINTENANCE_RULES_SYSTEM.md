# Rules-Based Maintenance Tracking System

## Overview

This is a comprehensive, **dynamic maintenance tracking system** that automatically calculates when maintenance is due based on:

- **Maintenance Rules** (stored once, reused forever)
- **Vessel State** (engine hours, trips, dates)
- **Maintenance Logs** (history of when work was done)

The system **learns the rules once**, then continuously tracks and compares against those rules to determine what needs maintenance.

---

## 🎯 Key Concept

### Traditional Approach (Static)

- Frontend has hardcoded tasks like "Oil change due in 15 hours"
- No automatic tracking of engine hours or trips
- Manual updates required

### Our Approach (Rules-Based)

```
Rules (teach once) + Current State (auto-tracked) = Dynamic Status (calculated)
```

Example:

```
Rule: "Engine oil every 100 hours, warn 20 hours before"
Last service: 1200 engine hours
Current: 1240 engine hours
Result: "Due in 60 hours" (status: OK)

When engine reaches 1281 hours → "Due in 19 hours" (status: DUE_SOON)
When engine reaches 1300+ hours → "Overdue by X hours" (status: OVERDUE)
```

---

## 📊 System Architecture

### Database Collections

#### 1. **maintenance_rules**

Stores the rules for when maintenance should be performed.

```json
{
  "_id": ObjectId("..."),
  "userId": "user123",
  "system_id": "engine",
  "part_name": "Engine oil",
  "trigger_type": "hours",      // hours | days | trips | sensor
  "interval_value": 100,         // Every 100 hours
  "warning_before": 20,          // Warn 20 hours before
  "description": "Regular engine oil change",
  "created_at": "2025-11-30T..."
}
```

#### 2. **vessel_states**

Tracks current counters for each vessel.

```json
{
  "_id": ObjectId("..."),
  "vessel_id": "IDAY",
  "engine_hours": 1240,
  "total_trips": 57,
  "last_trip_date": "2025-11-29",
  "sensor_data": {},
  "updated_at": "2025-11-30T..."
}
```

#### 3. **maintenance_logs**

Records when maintenance was performed.

```json
{
  "_id": ObjectId("..."),
  "vessel_id": "IDAY",
  "system_id": "engine",
  "part_name": "Engine oil",
  "done_at": "2025-11-20",
  "technician": "John Smith",
  "notes": "Changed oil and filter",
  "cost": "$120",
  "engine_hours_at_service": 1200,
  "trips_at_service": 55,
  "created_at": "2025-11-20T..."
}
```

---

## 🔧 API Endpoints

### Base URL

```
http://localhost:8000/api/v1/maintenance-rules
```

All endpoints require JWT authentication via `Authorization: Bearer <token>` header.

---

### 1️⃣ Maintenance Rules

#### GET `/rules`

Get all maintenance rules (optionally filtered by system).

**Query Parameters:**

- `system_id` (optional): Filter by system (e.g., "engine")

**Response:**

```json
[
  {
    "id": "rule123",
    "system_id": "engine",
    "part_name": "Engine oil",
    "trigger_type": "hours",
    "interval_value": 100,
    "warning_before": 20,
    "description": "Regular engine oil change"
  }
]
```

---

#### POST `/rules`

Create a new maintenance rule.

**Request Body:**

```json
{
  "system_id": "engine",
  "part_name": "Fuel filter",
  "trigger_type": "hours",
  "interval_value": 300,
  "warning_before": 30,
  "description": "Fuel filter replacement"
}
```

---

#### PUT `/rules/{rule_id}`

Update an existing rule.

**Request Body:**

```json
{
  "interval_value": 120,
  "warning_before": 25
}
```

---

#### DELETE `/rules/{rule_id}`

Delete a rule.

---

### 2️⃣ Vessel State

#### GET `/vessels/{vessel_id}/state`

Get current state/counters for a vessel.

**Response:**

```json
{
  "vessel_id": "IDAY",
  "engine_hours": 1240,
  "total_trips": 57,
  "last_trip_date": "2025-11-29",
  "updated_at": "2025-11-30T..."
}
```

---

#### PATCH `/vessels/{vessel_id}/state`

Manually update vessel state counters.

**Request Body:**

```json
{
  "engine_hours": 1250,
  "total_trips": 58
}
```

---

#### POST `/vessels/{vessel_id}/complete-trip`

Automatically update counters after completing a trip.

**Query Parameters:**

- `trip_duration_hours`: How many engine hours this trip took (e.g., 5.5)
- `trip_date`: Date of the trip (ISO format, e.g., "2025-11-30")

**Example:**

```
POST /vessels/IDAY/complete-trip?trip_duration_hours=5.5&trip_date=2025-11-30
```

**Response:**

```json
{
  "message": "Trip completed successfully",
  "state": {
    "vessel_id": "IDAY",
    "engine_hours": 1245, // Incremented by 5
    "total_trips": 58, // Incremented by 1
    "last_trip_date": "2025-11-30"
  }
}
```

---

### 3️⃣ Maintenance Logs

#### GET `/vessels/{vessel_id}/logs`

Get maintenance logs for a vessel.

**Query Parameters:**

- `system_id` (optional): Filter by system
- `part_name` (optional): Filter by part
- `limit` (optional, default 100): Max number of logs

**Response:**

```json
[
  {
    "id": "log123",
    "vessel_id": "IDAY",
    "system_id": "engine",
    "part_name": "Engine oil",
    "done_at": "2025-11-20",
    "technician": "John Smith",
    "notes": "Changed oil and filter",
    "cost": "$120",
    "engine_hours_at_service": 1200,
    "trips_at_service": 55
  }
]
```

---

#### POST `/vessels/{vessel_id}/logs`

Log that maintenance was performed.

**Request Body:**

```json
{
  "system_id": "engine",
  "part_name": "Engine oil",
  "done_at": "2025-11-30",
  "technician": "John Smith",
  "notes": "Changed oil and filter",
  "cost": "$120"
  // engine_hours_at_service and trips_at_service auto-filled from current state
}
```

**What happens:**

- Creates a new log entry
- Resets the maintenance countdown for that part
- Next time summary is calculated, it uses this log as the "last service"

---

### 4️⃣ Maintenance Summary (THE MAIN ONE ⭐)

#### GET `/vessels/{vessel_id}/summary`

**The most important endpoint!** Calculates real-time maintenance status for entire vessel.

**Response:**

```json
{
  "vessel_id": "IDAY",
  "vessel_name": "IDAY-Coastal",
  "state": {
    "vessel_id": "IDAY",
    "engine_hours": 1240,
    "total_trips": 57,
    "last_trip_date": "2025-11-29"
  },
  "systems": [
    {
      "system_id": "engine",
      "system_name": "Main Engine",
      "status": "due_soon",
      "summary_message": "Engine oil change due in 18 hours",
      "parts": [
        {
          "name": "Engine oil",
          "status": "due_soon",
          "trigger_type": "hours",
          "current_value": 1240,
          "due_at_value": 1300,
          "remaining": 60,
          "message": "Engine oil due in 60 hours",
          "last_service": {
            "done_at": "2025-11-20",
            "technician": "John Smith",
            "notes": "Changed oil and filter",
            "engine_hours_at_service": 1200
          }
        },
        {
          "name": "Fuel filter",
          "status": "ok",
          "trigger_type": "hours",
          "current_value": 1240,
          "due_at_value": 1500,
          "remaining": 260,
          "message": "Fuel filter due in 260 hours"
        }
      ]
    },
    {
      "system_id": "nets",
      "system_name": "Nets & Gear",
      "status": "operational",
      "summary_message": "All systems operational",
      "parts": [
        {
          "name": "Net inspection",
          "status": "ok",
          "trigger_type": "trips",
          "current_value": 57,
          "due_at_value": 60,
          "remaining": 3,
          "message": "Net inspection due in 3 trips"
        }
      ]
    }
  ],
  "overall_status": "due_soon",
  "generated_at": "2025-11-30T12:34:56"
}
```

**Calculation Logic:**

1. Fetches all rules for the user
2. Fetches vessel state (engine hours, trips)
3. Fetches all maintenance logs
4. For each rule:
   - Gets most recent log for that part
   - Calculates: `remaining = (last_service + interval) - current_value`
   - Sets status: `overdue` (≤0), `due_soon` (≤warning), or `ok`
5. Aggregates system status (worst part determines system status)
6. Returns complete summary

---

### 5️⃣ Seed Default Rules

#### POST `/seed-default-rules`

Create default maintenance rules for a new user.

**Response:**

```json
{
  "message": "Default maintenance rules created successfully",
  "count": 5,
  "rules": [
    {
      "system": "engine",
      "part": "Engine oil",
      "type": "hours",
      "interval": 100
    },
    {
      "system": "engine",
      "part": "Fuel filter",
      "type": "hours",
      "interval": 300
    },
    {
      "system": "nets",
      "part": "Net inspection",
      "type": "trips",
      "interval": 3
    },
    {
      "system": "safety",
      "part": "Lifejacket check",
      "type": "days",
      "interval": 180
    },
    {
      "system": "electronics",
      "part": "Battery check",
      "type": "days",
      "interval": 365
    }
  ]
}
```

---

## 🎨 Frontend Integration

### Redux Store Structure

```typescript
{
  maintenanceRules: {
    rules: MaintenanceRule[],
    vesselStates: Record<vesselId, VesselState>,
    summaries: Record<vesselId, VesselMaintenanceSummary>,
    logs: Record<vesselId, MaintenanceLog[]>,
    loading: boolean,
    error: string | null
  }
}
```

### Main Component: `MaintenanceTracking.tsx`

**Features:**

- Vessel selector
- Real-time status display (green/yellow/red)
- Systems list with status badges
- Detailed part information with counters
- Last service history
- Auto-refresh capability

**Usage:**

```tsx
import MaintenanceTracking from "@/pages/MaintenanceTracking";

// In your router
<Route path="/maintenance-tracking" element={<MaintenanceTracking />} />;
```

---

## 🔄 Typical Workflow

### 1. **Initial Setup (One Time)**

```bash
# User logs in
POST /api/v1/auth/login

# System seeds default rules
POST /api/v1/maintenance-rules/seed-default-rules

# Result: 5 default rules created (Engine, Nets, Safety, Electronics)
```

---

### 2. **User Opens Maintenance Page**

```bash
# Frontend fetches summary
GET /api/v1/maintenance-rules/vessels/IDAY/summary

# Backend calculates:
# - Reads vessel state: 1240 engine hours, 57 trips
# - Reads rules: Engine oil every 100h, Net inspection every 3 trips, etc.
# - Reads logs: Last oil change at 1200h
# - Calculates: Oil due in 60 hours (OK), Nets due in 3 trips (OK)
# - Returns complete summary with status for each part
```

---

### 3. **User Completes a Trip**

```bash
# Log trip completion
POST /api/v1/maintenance-rules/vessels/IDAY/complete-trip?trip_duration_hours=5&trip_date=2025-11-30

# Result:
# - engine_hours: 1240 → 1245 (+5)
# - total_trips: 57 → 58 (+1)
# - last_trip_date: "2025-11-30"
```

**Next time summary is fetched:**

- Engine oil: Due in 55 hours (was 60)
- Net inspection: Due in 2 trips (was 3)

---

### 4. **User Performs Maintenance**

```bash
# Log that oil was changed
POST /api/v1/maintenance-rules/vessels/IDAY/logs
{
  "system_id": "engine",
  "part_name": "Engine oil",
  "done_at": "2025-11-30",
  "technician": "John Smith",
  "notes": "Changed oil and filter",
  "cost": "$120"
}

# Backend auto-fills:
# - engine_hours_at_service: 1245 (from current state)
```

**Next time summary is fetched:**

- Engine oil: Due in 100 hours (reset to full interval)

---

## 📈 Status Calculation Examples

### Hours-Based (Engine Oil)

```python
Rule: interval = 100 hours, warning = 20 hours
Last service: 1200 hours
Current: 1240 hours

due_at = 1200 + 100 = 1300
remaining = 1300 - 1240 = 60

Status: OK (60 > 20)
Message: "Engine oil due in 60 hours"
```

### Trips-Based (Net Inspection)

```python
Rule: interval = 3 trips, warning = 1 trip
Last service: 54 trips
Current: 57 trips

due_at = 54 + 3 = 57
remaining = 57 - 57 = 0

Status: OVERDUE (0 ≤ 0)
Message: "Net inspection is overdue by 0 trips"
```

### Days-Based (Lifejacket Check)

```python
Rule: interval = 180 days, warning = 14 days
Last service: 2025-06-01
Current date: 2025-11-30

days_since = (2025-11-30) - (2025-06-01) = 182 days
due_at = 0 + 180 = 180
remaining = 180 - 182 = -2

Status: OVERDUE (-2 ≤ 0)
Message: "Lifejacket check is overdue by 2 days"
```

---

## 🚀 Future Enhancements

### IoT Sensor Integration

```json
{
  "system_id": "engine",
  "part_name": "Engine temperature monitor",
  "trigger_type": "sensor",
  "interval_value": 0, // Not used for sensors
  "warning_before": 0,
  "description": "Alert if engine temp > 90°C for 10 minutes"
}
```

**Calculation logic:**

```python
if trigger_type == "sensor":
    sensor_value = vessel_state.sensor_data.get("engine_temp")
    if sensor_value > 90:
        status = "critical"
        message = f"Engine temperature critical: {sensor_value}°C"
```

---

## 🧪 Testing

### 1. Seed Rules

```bash
curl -X POST http://localhost:8000/api/v1/maintenance-rules/seed-default-rules \
  -H "Authorization: Bearer <token>"
```

### 2. Get Summary

```bash
curl http://localhost:8000/api/v1/maintenance-rules/vessels/IDAY/summary \
  -H "Authorization: Bearer <token>"
```

### 3. Complete a Trip

```bash
curl -X POST "http://localhost:8000/api/v1/maintenance-rules/vessels/IDAY/complete-trip?trip_duration_hours=5&trip_date=2025-11-30" \
  -H "Authorization: Bearer <token>"
```

### 4. Log Maintenance

```bash
curl -X POST http://localhost:8000/api/v1/maintenance-rules/vessels/IDAY/logs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "system_id": "engine",
    "part_name": "Engine oil",
    "done_at": "2025-11-30",
    "technician": "John Smith",
    "notes": "Oil change",
    "cost": "$120"
  }'
```

---

## 📝 Summary

This system provides:

✅ **One-time rule setup** - Define maintenance intervals once  
✅ **Automatic tracking** - Engine hours, trips, dates tracked automatically  
✅ **Real-time calculation** - Status calculated on-demand based on current state  
✅ **Historical logging** - Full maintenance history preserved  
✅ **Multi-trigger support** - Hours, days, trips, sensors  
✅ **Smart warnings** - Configurable warning thresholds  
✅ **REST API** - Easy integration with any frontend  
✅ **User isolation** - Each user has their own rules and logs

The system **learns once, tracks forever** - a true rule-based maintenance tracker!
