from sqlalchemy.orm import declarative_base

Base = declarative_base()

def init_models():
    # Import models to ensure they are registered with Base metadata
    try:
        from app.models import user, trip  # noqa: F401
    except Exception:
        pass
