from typing import Optional
import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

MONGO_URI = os.environ.get("MONGODB_URI") or "mongodb://localhost:27017"
MONGO_DB_NAME = os.environ.get("MONGODB_DB") or "finfinder"

print(f"🔗 MongoDB URI: {MONGO_URI[:50]}..." if len(MONGO_URI) > 50 else f"🔗 MongoDB URI: {MONGO_URI}")
print(f"📦 MongoDB Database: {MONGO_DB_NAME}")

_client: Optional[AsyncIOMotorClient] = None

def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000
        )
    return _client

def get_database() -> AsyncIOMotorDatabase:
    client = get_client()
    return client[MONGO_DB_NAME]

async def get_db_async() -> AsyncIOMotorDatabase:
    """Async function to get database instance."""
    return get_database()

async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
