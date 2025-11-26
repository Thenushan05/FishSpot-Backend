from typing import Optional
import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

MONGO_URI = os.environ.get("MONGODB_URI") or "mongodb://localhost:27017"
MONGO_DB_NAME = os.environ.get("MONGODB_DB") or "finfinder"

_client: Optional[AsyncIOMotorClient] = None

def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client

def get_database() -> AsyncIOMotorDatabase:
    client = get_client()
    return client[MONGO_DB_NAME]

async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
