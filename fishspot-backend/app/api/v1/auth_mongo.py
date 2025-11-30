from fastapi import APIRouter, HTTPException, status, Request
from starlette.responses import JSONResponse
from datetime import datetime
from bson import ObjectId

from app.schemas.auth import Token, LoginIn, RegisterIn
from app.schemas.user import UserOut
from app.db.mongo import get_database
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token
from app.core.config import settings

router = APIRouter()


@router.post("/token", response_model=Token)
async def login_for_access_token(data: LoginIn):
    try:
        db = get_database()
        users_collection = db.users
        
        # Find user by email
        user = await users_collection.find_one({"email": data.email})
        if not user or not verify_password(data.password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid email or password"
            )

        user_id = str(user["_id"])
        access_token = create_access_token(subject=user_id)
        refresh_token = create_refresh_token(subject=user_id)

        # Set tokens as httpOnly cookies
        resp = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
        access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
        resp.set_cookie("access_token", access_token, httponly=True, samesite="lax", secure=False, max_age=access_max_age)
        resp.set_cookie("refresh_token", refresh_token, httponly=True, samesite="lax", secure=False, max_age=refresh_max_age)
        return resp
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )


@router.post("/register", response_model=Token)
async def register(data: RegisterIn):
    try:
        db = get_database()
        users_collection = db.users
        
        # Check if user already exists
        existing = await users_collection.find_one({"email": data.email})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Registration failed. Email may already be in use."
            )

        # Create new user document
        user_doc = {
            "email": data.email,
            "name": getattr(data, "name", None),
            "hashed_password": get_password_hash(data.password),
            "is_active": True,
            "role": "user",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await users_collection.insert_one(user_doc)
        user_id = str(result.inserted_id)

        access_token = create_access_token(subject=user_id)
        refresh_token = create_refresh_token(subject=user_id)
        
        resp = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
        access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
        resp.set_cookie("access_token", access_token, httponly=True, samesite="lax", secure=False, max_age=access_max_age)
        resp.set_cookie("refresh_token", refresh_token, httponly=True, samesite="lax", secure=False, max_age=refresh_max_age)
        return resp
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/refresh", response_model=Token)
async def refresh_token(request: Request):
    """Use the refresh_token cookie to mint a new access token and set it as cookie."""
    refresh = request.cookies.get("refresh_token")
    if not refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    
    try:
        payload = __import__('app.core.security', fromlist=['decode_access_token']).decode_access_token(refresh)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    access_token = create_access_token(subject=str(user_id))
    resp = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    resp.set_cookie("access_token", access_token, httponly=True, samesite="lax", secure=False, max_age=access_max_age)
    return resp


@router.post("/logout")
async def logout():
    resp = JSONResponse(content={"detail": "logged out"})
    resp.delete_cookie("access_token")
    resp.delete_cookie("refresh_token")
    return resp


@router.get("/me", response_model=UserOut)
async def read_current_user(
    current: dict = __import__('fastapi', fromlist=['Depends']).Depends(
        __import__('app.core.auth', fromlist=['get_current_user']).get_current_user
    )
):
    try:
        db = get_database()
        users_collection = db.users
        
        user_id = current.get("user_id")
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        return UserOut(
            id=str(user["_id"]),
            email=user["email"],
            name=user.get("name"),
            is_active=user.get("is_active", True),
            role=user.get("role", "user")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user: {str(e)}"
        )
