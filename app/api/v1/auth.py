from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import get_db
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    generate_api_key,
    get_current_active_user,
)
from app.domain.models.user import User
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.user import (
    UserCreate,
    UserResponse,
    LoginRequest,
    TokenResponse,
    ApiKeyResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


@router.post("/register", response_model=ApiResponse[UserResponse], status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Registers a new user and issues a dedicated programmatic API key.
    """
    # 1. Check email uniqueness
    stmt = select(User).where(User.email == user_in.email)
    res = await db.exec(stmt)
    if res.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    # 2. Check username uniqueness if provided
    if user_in.username:
        stmt = select(User).where(User.username == user_in.username)
        res = await db.exec(stmt)
        if res.first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this username already exists.",
            )

    # 3. Check telegram_id uniqueness if provided
    if user_in.telegram_id:
        stmt = select(User).where(User.telegram_id == user_in.telegram_id)
        res = await db.exec(stmt)
        if res.first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This Telegram ID is already registered to another account.",
            )

    user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role if user_in.role in ["user", "trader", "viewer"] else "user",
        telegram_id=user_in.telegram_id,
        api_key=generate_api_key("quant_user"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return ApiResponse(
        data=UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            telegram_id=user.telegram_id,
            api_key=user.api_key,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
    )


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticates user with email or username and password, returning JWT bearer token.
    """
    stmt = select(User).where(
        (User.email == req.email_or_username) | (User.username == req.email_or_username)
    )
    res = await db.exec(stmt)
    user = res.first()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive. Please contact system administrator.",
        )

    expires_delta = timedelta(days=7)
    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        expires_delta=expires_delta,
    )

    user_resp = UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        telegram_id=user.telegram_id,
        api_key=user.api_key,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )

    return ApiResponse(
        data=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in_seconds=int(expires_delta.total_seconds()),
            user=user_resp,
        )
    )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns the profile and API key of the currently authenticated user.
    """
    return ApiResponse(
        data=UserResponse(
            id=current_user.id,
            email=current_user.email,
            username=current_user.username,
            full_name=current_user.full_name,
            role=current_user.role,
            telegram_id=current_user.telegram_id,
            api_key=current_user.api_key,
            is_active=current_user.is_active,
            is_superuser=current_user.is_superuser,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at,
        )
    )


@router.post("/api-key/regenerate", response_model=ApiResponse[ApiKeyResponse])
async def regenerate_api_key(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revokes the current API key and issues a newly generated one.
    """
    new_key = generate_api_key("quant_user")
    current_user.api_key = new_key
    current_user.updated_at = datetime.now(timezone.utc)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return ApiResponse(
        data=ApiKeyResponse(
            api_key=new_key,
            created_at=current_user.updated_at,
        )
    )
