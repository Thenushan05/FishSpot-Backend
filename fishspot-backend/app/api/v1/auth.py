from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.schemas.auth import Token, LoginIn, RegisterIn
from app.schemas.user import UserOut
from app.db.session import get_db
from app.models.user import User
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token
from app.core.config import settings
from fastapi import Response

router = APIRouter()


@router.post("/token", response_model=Token)
def login_for_access_token(data: LoginIn, db: Session = Depends(get_db)):
    # ORM queries are parameterized by SQLAlchemy (safe against SQL injection)
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        # Return generic message to avoid user enumeration
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))

    # set tokens as httpOnly cookies (dev-friendly). Frontend should call with credentials included.
    resp = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    # cookie lifetimes in seconds
    access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
    resp.set_cookie("access_token", access_token, httponly=True, samesite="lax", secure=False, max_age=access_max_age)
    resp.set_cookie("refresh_token", refresh_token, httponly=True, samesite="lax", secure=False, max_age=refresh_max_age)
    return resp


@router.post("/register", response_model=Token)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    # Prevent overly large or malformed inputs (Pydantic already validates small size)
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        # Generic error to avoid leaking which emails are registered
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Registration failed")

    user = User(email=data.email, name=getattr(data, "name", None), hashed_password=get_password_hash(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))
    resp = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    access_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
    resp.set_cookie("access_token", access_token, httponly=True, samesite="lax", secure=False, max_age=access_max_age)
    resp.set_cookie("refresh_token", refresh_token, httponly=True, samesite="lax", secure=False, max_age=refresh_max_age)
    return resp



@router.post("/refresh", response_model=Token)
def refresh_token(response: Response, request: Request):
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
def logout():
    resp = JSONResponse(content={"detail": "logged out"})
    # clear cookies
    resp.delete_cookie("access_token")
    resp.delete_cookie("refresh_token")
    return resp


@router.get("/me", response_model=UserOut)
def read_current_user(current: dict = Depends(__import__('app.core.auth', fromlist=['get_current_user']).get_current_user), db: Session = Depends(get_db)):
    # current contains {'user_id': id, 'raw': payload}
    user_id = current.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.from_orm(user)


@router.exception_handler(Exception)
def _generic_exception_handler(request: Request, exc: Exception):
    # Always return a generic message for unexpected errors to avoid leaking internals
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
