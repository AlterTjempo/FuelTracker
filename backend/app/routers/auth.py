from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
import httpx
import re
import uuid

from database import get_db
from models import User
from config import settings
from limiter import limiter

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# --- Schemas ---

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    captcha_token: str | None = None


class LoginRequest(BaseModel):
    identifier: str  # email or username
    password: str


class UpdateProfileRequest(BaseModel):
    username: str | None = None
    email: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Helpers ---

def _bcrypt_safe(password: str) -> bytes:
    """bcrypt only uses the first 72 bytes; truncate to avoid raising on long input."""
    return password.encode("utf-8")[:72]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(_bcrypt_safe(plain_password), hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(_bcrypt_safe(password))


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User | None:
    if token is None:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    return user


def require_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin_user(user: User = Depends(require_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def validate_password(password: str) -> list[str]:
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain a lowercase letter")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain an uppercase letter")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_=+\[\]\\;'/`~]", password):
        errors.append("Password must contain at least one special character")
    return errors


async def verify_captcha(token: str) -> bool:
    if not settings.RECAPTCHA_SECRET_KEY:
        return True  # CAPTCHA disabled
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": settings.RECAPTCHA_SECRET_KEY,
                "response": token,
            },
        )
        result = response.json()
        return result.get("success", False)


# --- Endpoints ---

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)):
    # Validate CAPTCHA
    if settings.RECAPTCHA_SECRET_KEY:
        if not body.captcha_token:
            raise HTTPException(status_code=400, detail="CAPTCHA verification required")
        if not await verify_captcha(body.captcha_token):
            raise HTTPException(status_code=400, detail="CAPTCHA verification failed")

    # Validate email format
    if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", body.email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    # Validate password
    password_errors = validate_password(body.password)
    if password_errors:
        raise HTTPException(status_code=400, detail="; ".join(password_errors))

    # Validate username
    if not body.username or len(body.username.strip()) < 1:
        raise HTTPException(status_code=400, detail="Username is required")
    if len(body.username) > 50:
        raise HTTPException(status_code=400, detail="Username must be 50 characters or fewer")

    # Check if email already exists
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    # Create user
    user = User(
        id=uuid.uuid4(),
        username=body.username.strip(),
        email=body.email.lower().strip(),
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate token
    token = create_access_token(str(user.id))
    return TokenResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
        },
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    ident = body.identifier.strip()
    user = (
        db.query(User)
        .filter((User.email == ident.lower()) | (User.username == ident))
        .first()
    )
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return TokenResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
        },
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(require_current_user)):
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )


@router.post("/me/update", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    if body.username is not None:
        uname = body.username.strip()
        if len(uname) < 1:
            raise HTTPException(status_code=400, detail="Username is required")
        if len(uname) > 50:
            raise HTTPException(status_code=400, detail="Username must be 50 characters or fewer")
        user.username = uname

    if body.email is not None:
        new_email = body.email.lower().strip()
        if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", new_email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        existing = (
            db.query(User)
            .filter(User.email == new_email, User.id != user.id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        user.email = new_email

    db.commit()
    db.refresh(user)
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )


@router.post("/me/password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(require_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    password_errors = validate_password(body.new_password)
    if password_errors:
        raise HTTPException(status_code=400, detail="; ".join(password_errors))
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password updated successfully"}
