print("Starting FishSpot backend...")
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

# Import routers
from app.api.v1 import hotspots as hotspots_router
# chlo endpoint
try:
    from app.api.v1 import chlo_point as chlo_router
except Exception:
    chlo_router = None

# Mongo client integration
from app.db import mongo
from app.db.base import Base
from app.db.session import engine


def create_app() -> FastAPI:
    """Create FastAPI app and mount routers."""
    app = FastAPI(title="FishSpot Backend")

    # Custom exception handler to return errors as "error" instead of "detail"
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": "Validation error", "details": exc.errors()},
        )

    # Security headers + request limits
    @app.middleware("http")
    async def security_headers_and_body_limit(request, call_next):
        # Enforce a conservative maximum request body size (1 MiB) to reduce abuse
        MAX_BODY = 1_048_576
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY:
                    from starlette.responses import PlainTextResponse

                    return PlainTextResponse("Request payload too large", status_code=413)
            except Exception:
                pass

        response = await call_next(request)

        # Security-related response headers
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=()")
        # Content Security Policy - minimal default for APIs; frontends can supply stricter CSP
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; base-uri 'self'; connect-src 'self' http://localhost:8000 https://api.openweathermap.org; frame-ancestors 'none'; form-action 'self';")

        return response

    # CORS - allow local frontend dev origins
    # Accept origins from environment variable `ALLOW_ORIGINS` (comma-separated)
    # Fallback includes common localhost origins and 127.0.0.1 variants.
    import os
    import re
    from starlette.responses import JSONResponse

    env_origins = os.environ.get("ALLOW_ORIGINS")
    allow_origin_regex = None
    if env_origins:
        if env_origins.strip() == "*":
            # allow any origin (use regex so Access-Control-Allow-Origin echoes
            # the request origin and still permits credentials)
            allow_origin_regex = r".*"
            origins = []
        else:
            origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    else:
        # Development convenience: allow all origins by default to avoid CORS
        # issues during local testing. Set ALLOW_ORIGINS in environment to
        # restrict origins if needed.
        allow_origin_regex = r".*"
        origins = []

    # If allow_origin_regex is set, pass it to CORSMiddleware; otherwise pass explicit list.
    cors_kwargs = {
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["*"],
    }
    if allow_origin_regex:
        cors_kwargs["allow_origin_regex"] = allow_origin_regex
    else:
        cors_kwargs["allow_origins"] = origins

    app.add_middleware(CORSMiddleware, **cors_kwargs)

    # Helpful middleware: if an incoming request has an Origin header and that
    # origin is not allowed, return a clear JSON 403 explaining the CORS block.
    # This runs before route handlers but after CORSMiddleware; it just provides
    # friendlier messages for development when the origin isn't in the allowlist.
    def _is_origin_allowed(origin: str) -> bool:
        if not origin:
            return True
        if allow_origin_regex:
            try:
                return re.match(allow_origin_regex, origin) is not None
            except Exception:
                return False
        return origin in origins

    @app.middleware("http")
    async def _cors_check_middleware(request, call_next):
        origin = request.headers.get("origin")
        if origin and not _is_origin_allowed(origin):
            # Provide a clear error explaining why the browser is blocking the request.
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "CORS origin denied",
                    "origin": origin,
                    "allowed_origins": origins or ["*"],
                    "hint": "Set ALLOW_ORIGINS env or add this origin to your allowlist. For development you can set ALLOW_ORIGINS='*' but this may disable credentials with some browsers.",
                },
            )
        return await call_next(request)

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
        # MongoDB is the primary database - SQLite disabled
        print("✅ Using MongoDB for data storage")

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

    # ✅ Include MongoDB auth router
    try:
        from app.api.v1 import auth_mongo as auth_router
        app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
    except Exception as e:
        # Fallback to SQLite auth if MongoDB fails
        print(f"⚠️ MongoDB auth failed, using SQLite: {e}")
        try:
            from app.api.v1 import auth as auth_router
            app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
        except Exception:
            pass

    # ✅ Include simple health/db status endpoints
    try:
        from app.api.v1 import health as health_router
        app.include_router(health_router.router, prefix="/api/v1/health", tags=["health"])
    except Exception:
        pass

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

    # maintenance router (original - static vessel data)
    try:
        from app.api.v1 import maintenance as maintenance_router
        app.include_router(
            maintenance_router.router,
            prefix="/api/v1/maintenance",
            tags=["maintenance"]
        )
        print("✅ Maintenance router registered at /api/v1/maintenance")
    except Exception as e:
        print(f"⚠️ Failed to load maintenance router: {e}")
        pass

    # maintenance rules router (NEW - dynamic rule-based tracking)
    try:
        from app.api.v1 import maintenance_rules as maintenance_rules_router
        app.include_router(
            maintenance_rules_router.router,
            prefix="/api/v1/maintenance-rules",
            tags=["maintenance-rules"]
        )
        print("✅ Maintenance rules router registered at /api/v1/maintenance-rules")
    except Exception as e:
        print(f"⚠️ Failed to load maintenance rules router: {e}")
        pass

    return app


app = create_app()
