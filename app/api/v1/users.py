from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import get_db
from app.core.auth import get_current_active_user, get_current_admin, hash_password
from app.domain.models.user import User
from app.domain.schemas.common import ApiResponse
from app.domain.schemas.user import UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["User Administration"])


@router.get("", response_model=ApiResponse[List[UserResponse]])
async def list_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """
    Lists registered users (Administrator only).
    """
    stmt = select(User).order_by(desc(User.created_at)).offset(offset).limit(limit)
    res = await db.exec(stmt)
    users = res.all()

    items = [
        UserResponse(
            id=u.id,
            email=u.email,
            username=u.username,
            full_name=u.full_name,
            role=u.role,
            telegram_id=u.telegram_id,
            api_key=u.api_key,
            is_active=u.is_active,
            is_superuser=u.is_superuser,
            created_at=u.created_at,
            updated_at=u.updated_at,
        )
        for u in users
    ]
    return ApiResponse(data=items)


@router.get("/{user_id}", response_model=ApiResponse[UserResponse])
async def get_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Only admins or the user themselves can view this profile
    if current_user.id != user_id and current_user.role != "admin" and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access other users' profile.",
        )

    stmt = select(User).where(User.id == user_id)
    res = await db.exec(stmt)
    user = res.first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")

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


@router.put("/{user_id}", response_model=ApiResponse[UserResponse])
async def update_user(
    user_id: int,
    update_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    is_admin = current_user.role == "admin" or current_user.is_superuser
    if current_user.id != user_id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update other users' profile.",
        )

    stmt = select(User).where(User.id == user_id)
    res = await db.exec(stmt)
    user = res.first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")

    if update_in.email is not None:
        user.email = update_in.email
    if update_in.username is not None:
        user.username = update_in.username
    if update_in.full_name is not None:
        user.full_name = update_in.full_name
    if update_in.telegram_id is not None:
        user.telegram_id = update_in.telegram_id
    if update_in.password is not None:
        user.hashed_password = hash_password(update_in.password)

    # Only admins can change roles and active status
    if is_admin:
        if update_in.role is not None:
            user.role = update_in.role
        if update_in.is_active is not None:
            user.is_active = update_in.is_active

    user.updated_at = datetime.now(timezone.utc)
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
