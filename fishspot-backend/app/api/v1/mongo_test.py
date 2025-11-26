from fastapi import APIRouter, Depends, HTTPException
from app.db.mongo import get_database

router = APIRouter()


def get_db_dep():
    # return the motor database instance
    return get_database()


@router.get("/ping")
async def ping_db(db=Depends(get_db_dep)):
    try:
        # run a lightweight command
        res = await db.command({"ping": 1})
        return {"ok": bool(res.get("ok", 0)), "res": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-collection")
async def test_collection(db=Depends(get_db_dep)):
    # show a sample of collection names
    try:
        names = await db.list_collection_names()
        return {"collections": names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
