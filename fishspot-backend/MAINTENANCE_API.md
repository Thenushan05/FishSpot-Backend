# Maintenance System Integration

## Overview

Backend API and Redux integration for the vessel maintenance tracking system. Allows users to manage their fishing vessels, systems, maintenance tasks, and service logs.

## Backend API

### Base URL

```
http://localhost:8000/api/v1/maintenance
```

### Endpoints

#### Vessels

**GET /vessels**

- Get all vessels for current user
- Auth required
- Response: `{ vessels: Vessel[] }`

**GET /vessels/:vesselId**

- Get specific vessel by ID
- Auth required
- Response: `Vessel`

**POST /vessels**

- Create new vessel
- Auth required
- Body: `Vessel` (without id)
- Response: `{ id: string, message: string }`

**PUT /vessels/:vesselId**

- Update existing vessel
- Auth required
- Body: `Vessel`
- Response: `{ message: string }`

**DELETE /vessels/:vesselId**

- Delete vessel
- Auth required
- Response: `{ message: string }`

#### System Status

**PATCH /vessels/:vesselId/systems/:systemId/status**

- Update system status
- Auth required
- Body: `{ status: "operational" | "due-soon" | "overdue" | "critical" | "offline" }`
- Response: `{ message: string }`

#### Tasks

**POST /vessels/:vesselId/systems/:systemId/tasks**

- Create maintenance task
- Auth required
- Body: `{ systemId: string, task: string, due: string, priority: "low" | "medium" | "high" }`
- Response: `{ id: string, message: string }`

**PATCH /vessels/:vesselId/systems/:systemId/tasks/:taskId**

- Update task
- Auth required
- Body: `{ task?: string, due?: string, priority?: string, completed?: boolean }`
- Response: `{ message: string }`

**DELETE /vessels/:vesselId/systems/:systemId/tasks/:taskId**

- Delete task
- Auth required
- Response: `{ message: string }`

#### Service Logs

**POST /vessels/:vesselId/systems/:systemId/service-logs**

- Add service log
- Auth required
- Body: `{ systemId: string, date: string, technician: string, notes: string, cost?: string }`
- Response: `{ message: string }`

## Frontend Integration

### Redux Store

The maintenance slice is integrated into the Redux store at `store.maintenance`.

#### State Structure

```typescript
{
  vessels: Vessel[];
  selectedVesselId: string | null;
  loading: boolean;
  error: string | null;
}
```

#### Actions

Import from `@/store/maintenanceSlice`:

```typescript
import {
  fetchVessels,
  fetchVessel,
  createVessel,
  updateVessel,
  deleteVessel,
  updateSystemStatus,
  createTask,
  updateTask,
  deleteTask,
  createServiceLog,
  setSelectedVessel,
  clearError,
} from "@/store/maintenanceSlice";
```

### Usage Example

```typescript
import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { fetchVessels } from "@/store/maintenanceSlice";
import { RootState, AppDispatch } from "@/store";

function MaintenancePage() {
  const dispatch = useDispatch<AppDispatch>();
  const { vessels, loading, error } = useSelector(
    (state: RootState) => state.maintenance
  );

  useEffect(() => {
    dispatch(fetchVessels());
  }, [dispatch]);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      {vessels.map((vessel) => (
        <div key={vessel.id}>{vessel.name}</div>
      ))}
    </div>
  );
}
```

### API Helper Functions

Direct API calls available in `@/services/api`:

```typescript
import {
  getVessels,
  getVessel,
  createVessel,
  updateVessel,
  deleteVessel,
  updateSystemStatus,
  createMaintenanceTask,
  updateMaintenanceTask,
  deleteMaintenanceTask,
  createServiceLog,
} from "@/services/api";
```

## Data Models

### Vessel

```typescript
{
  id: string;
  name: string;
  type: string;
  stats: {
    lastTrip: string;
    engineHours: number;
    fuelOnBoard: string;
    iceCapacity: string;
    nextServiceDue: string;
  };
  systems: FishingSystem[];
}
```

### FishingSystem

```typescript
{
  id: string;
  name: string;
  status: "operational" | "due-soon" | "overdue" | "critical" | "offline";
  description: string;
  blueprintImage: string;
  specs: Record<string, string | { value: string; status: "good" | "warning" | "critical" }>;
  upcomingTasks: MaintenanceTask[];
  lastService: ServiceLog;
  aiTips?: string[];
  subParts?: SubPart[];
}
```

### MaintenanceTask

```typescript
{
  id: string;
  task: string;
  due: string;
  priority: "low" | "medium" | "high";
}
```

### ServiceLog

```typescript
{
  date: string;
  technician: string;
  notes: string;
  cost?: string;
}
```

## Database

Vessels are stored in MongoDB in the `vessels` collection with the following structure:

- Each vessel is linked to a user via `userId` field
- Systems are embedded in the vessel document
- Tasks are embedded in each system
- Service logs are embedded in each system

## Authentication

All endpoints require authentication. Include JWT token in:

- Authorization header: `Bearer <token>`
- Or set `withCredentials: true` for cookie-based auth

## Error Handling

All API responses use consistent error format:

```json
{
  "error": "Error message here"
}
```

Redux thunks handle errors and store them in `state.maintenance.error`.

## Testing

To test the API:

1. Start backend: `uvicorn app.main:app --reload --port 8000`
2. Login to get auth token
3. Use Postman/Thunder Client to test endpoints
4. Or use the frontend with Redux DevTools to monitor state changes

## Future Enhancements

- [ ] Real-time updates with WebSockets
- [ ] File upload for service receipts/photos
- [ ] Automated task scheduling based on engine hours
- [ ] Integration with FishSpot AI for predictive maintenance
- [ ] Export maintenance logs to PDF
- [ ] Multi-vessel comparison dashboard
