from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from app.api.v1 import hotspots as hotspots_router
# chlo endpoint
try:
    from app.api.v1 import chlo_point as chlo_router
except Exception:
    chlo_router = None

# Mongo client integration
from app.db import mongo


def create_app() -> FastAPI:
    """Create FastAPI app and mount routers."""
    app = FastAPI(title="FishSpot Backend")

    # CORS - allow local frontend dev origins
    # Accept origins from environment variable `ALLOW_ORIGINS` (comma-separated)
    # Fallback includes common localhost origins and 127.0.0.1 variants.
    import os

    env_origins = os.environ.get("ALLOW_ORIGINS")
    if env_origins:
        origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    else:
        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost",
        ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Connect to Mongo on startup, close on shutdown
    @app.on_event("startup")
    async def _startup_db():
        try:
            # initialize client
            mongo.get_client()
            # optional quick ping
            await app.state.__dict__.setdefault('mongodb_ping', None)
        except Exception:
            # don't crash app creation on db connection error; log if needed
            pass

    @app.on_event("shutdown")
    async def _shutdown_db():
        try:
            await mongo.close_client()
        except Exception:
            pass

    # ✅ Include hotspots API (your model endpoint)
    app.include_router(
        hotspots_router.router,
        prefix="/api/v1/hotspots",
        tags=["hotspots"],
    )

    # ✅ Optionally include agent API if it exists
    try:
        from app.api.v1 import agent as agent_router
        app.include_router(
            agent_router.router,
            prefix="/api/v1/agent",
            tags=["agent"],
        )
    except ImportError:
        # Agent router might not exist yet during early development
        pass

    # ✅ Include chlo endpoint if available
    if chlo_router is not None:
        app.include_router(
            chlo_router.router,
            prefix="/api/v1/chlo",
            tags=["chlo"],
        )

    # include a lightweight mongo test route (optional)
    try:
        from app.api.v1 import mongo_test as mongo_test_router
        app.include_router(
            mongo_test_router.router,
            prefix="/api/v1/db",
            tags=["db"],
        )
    except Exception:
        pass

    # Mount new hotspots router (simple ML endpoints)
    try:
        from app.api import hotspots as hotspots_router_new
        app.include_router(hotspots_router_new.router, prefix="/api/hotspots", tags=["hotspots"])
    except Exception:
        # ok if router not present
        pass

    # depth lookup router
    try:
        from app.api import depth as depth_router
        app.include_router(depth_router.router, prefix="/api/depth", tags=["depth"])
    except Exception:
        pass

    return app


app = create_app()
