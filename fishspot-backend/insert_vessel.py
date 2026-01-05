"""
Quick script to manually insert a test vessel into MongoDB
Run this with: python insert_vessel.py
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime

# MongoDB connection (update if needed)
MONGO_URI = "mongodb+srv://thenuthamizh05_db_user:67hMEba0C3uXm@fishspotcluster.sxn1r.mongodb.net/?retryWrites=true&w=majority&appName=FishSpotCluster"
DB_NAME = "ocelyne"

async def insert_vessel():
    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    # You need a valid user_id - let's fetch the first user
    users = db.users
    user = await users.find_one()
    
    if not user:
        print("❌ No users found! Please create a user first by logging in.")
        return
    
    user_id = str(user["_id"])
    print(f"✓ Found user: {user.get('email')} (ID: {user_id})")
    
    # Create a test vessel
    vessel = {
        "name": "IMUL-001",
        "type": "Multi-Day Vessel",
        "userId": user_id,
        "stats": {
            "lastTrip": "2025-11-28",
            "engineHours": 0,
            "fuelOnBoard": "8,500 L",
            "iceCapacity": "85%",
            "nextServiceDue": "Not scheduled"
        },
        "systems": [
            {
                "id": "engine",
                "name": "Engine & Propulsion",
                "status": "operational",
                "description": "Main inboard diesel engine and transmission.",
                "specs": {
                    "Oil Level": "Good",
                    "Coolant Temp": "80°C",
                    "RPM (Idle)": "750"
                },
                "upcomingTasks": [],
                "lastService": {
                    "date": "2025-11-10",
                    "technician": "J. Silva",
                    "notes": "Initial setup"
                }
            },
            {
                "id": "nets",
                "name": "Nets & Gear",
                "status": "operational",
                "description": "Winches, drums, and fishing nets.",
                "specs": {
                    "Net Condition": "Good",
                    "Winch Pressure": "150 bar"
                },
                "upcomingTasks": [],
                "lastService": {
                    "date": "2025-11-20",
                    "technician": "Crew",
                    "notes": "Initial setup"
                }
            },
            {
                "id": "safety",
                "name": "Safety & Compliance",
                "status": "operational",
                "description": "Life saving appliances",
                "specs": {
                    "Life Raft": "Certified",
                    "Flares": "Valid"
                },
                "upcomingTasks": [],
                "lastService": {
                    "date": "2025-06-01",
                    "technician": "SafetyFirst",
                    "notes": "Initial setup"
                }
            },
            {
                "id": "electronics",
                "name": "Electronics & Sensors",
                "status": "operational",
                "description": "Navigation and communication",
                "specs": {
                    "GPS": "Locked (12 sats)",
                    "Battery": "24.2 V"
                },
                "upcomingTasks": [],
                "lastService": {
                    "date": "2025-09-01",
                    "technician": "ElectroMarine",
                    "notes": "Initial setup"
                }
            }
        ]
    }
    
    # Insert vessel
    vessels = db.vessels
    result = await vessels.insert_one(vessel)
    vessel_id = str(result.inserted_id)
    
    print(f"✅ Vessel inserted successfully!")
    print(f"   Vessel ID: {vessel_id}")
    print(f"   Vessel Name: {vessel['name']}")
    print(f"   User ID: {user_id}")
    
    # Initialize vessel state
    vessel_state = {
        "vessel_id": vessel_id,
        "userId": user_id,
        "engine_hours": 0,
        "total_trips": 0,
        "last_trip_date": None,
        "sensor_data": None,
        "updated_at": datetime.now()
    }
    
    await db.vessel_states.insert_one(vessel_state)
    print(f"✅ Vessel state initialized (0 hours, 0 trips)")
    
    client.close()
    print("\n🎉 Done! You can now access the vessel at http://localhost:8080/maintenance-tracking")

if __name__ == "__main__":
    asyncio.run(insert_vessel())
