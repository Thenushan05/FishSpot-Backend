from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy import text
from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/db")
def db_status(db=Depends(get_db)):
    """Attempt a lightweight DB query to verify the SQL database is available."""
    try:
        # get_db yields a session; perform a trivial SELECT 1
        res = db.execute(text("SELECT 1 as value")).fetchone()
        return {"db": "ok", "value": int(res[0])}
    except Exception as e:
        return {"db": "error", "detail": str(e)}
