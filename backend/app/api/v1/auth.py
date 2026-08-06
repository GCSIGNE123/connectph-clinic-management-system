"""Authentication endpoints."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.core.rate_limit import rate_limit_forgot_password, rate_limit_login
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MeBranch,
    MeClinic,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, raw_refresh_token: str, *, remember_me: bool) -> None:
    max_age_days = (
        settings.REFRESH_TOKEN_EXPIRE_DAYS_REMEMBER_ME if remember_me else settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=raw_refresh_token,
        max_age=max_age_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit_login)])
async def login(
    payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    service = AuthService(db)
    result = await service.login(
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result.refresh_token, remember_me=payload.remember_me)
    role_name = result.user.role.name if result.user.role is not None else None
    return TokenResponse(
        access_token=result.access_token,
        user_id=result.user.id,
        clinic_id=result.user.clinic_id,
        role=role_name,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    service = AuthService(db)
    result = await service.register(payload)
    _set_refresh_cookie(response, result.refresh_token, remember_me=False)
    role_name = result.user.role.name if result.user.role is not None else None
    return TokenResponse(
        access_token=result.access_token,
        user_id=result.user.id,
        clinic_id=result.user.clinic_id,
        role=role_name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token_cookie: str | None = Cookie(default=None, alias=settings.REFRESH_TOKEN_COOKIE_NAME),
) -> TokenResponse:
    raw_refresh_token = payload.refresh_token or refresh_token_cookie
    if not raw_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided")

    service = AuthService(db)
    result = await service.refresh(
        raw_refresh_token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result.refresh_token, remember_me=False)
    role_name = result.user.role.name if result.user.role is not None else None
    return TokenResponse(
        access_token=result.access_token,
        user_id=result.user.id,
        clinic_id=result.user.clinic_id,
        role=role_name,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    refresh_token_cookie: str | None = Cookie(default=None, alias=settings.REFRESH_TOKEN_COOKIE_NAME),
) -> None:
    service = AuthService(db)
    await service.logout(refresh_token_cookie, user_id=current_user.id)
    _clear_refresh_cookie(response)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(rate_limit_forgot_password)])
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    service = AuthService(db)
    await service.forgot_password(payload.email)
    return {"detail": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    service = AuthService(db)
    await service.reset_password(payload.token, payload.new_password)
    return {"detail": "Password has been reset."}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    service = AuthService(db)
    await service.verify_email(payload.token)
    return {"detail": "Email verified."}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    payload: ResendVerificationRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    service = AuthService(db)
    await service.resend_verification(payload.email)
    return {"detail": "If the account exists and is unverified, a verification email has been sent."}


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    """Return the authenticated user's profile, including clinic and branch context."""
    from sqlalchemy import select  # noqa: PLC0415

    from app.models.branch import Branch  # noqa: PLC0415
    from app.models.clinic import Clinic  # noqa: PLC0415

    clinic = (
        await db.execute(select(Clinic).where(Clinic.id == current_user.clinic_id))
    ).scalar_one_or_none()
    branch = None
    if current_user.branch_id is not None:
        branch = (
            await db.execute(select(Branch).where(Branch.id == current_user.branch_id))
        ).scalar_one_or_none()

    role_name = current_user.role.name if current_user.role is not None else "Viewer"

    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=role_name,
        clinic_id=current_user.clinic_id,
        clinic=(
            MeClinic(
                id=clinic.id,
                name=clinic.name,
                slug=clinic.slug,
                logo_url=clinic.logo_url,
                timezone=clinic.timezone,
                created_at=clinic.created_at.isoformat(),
            )
            if clinic is not None
            else None
        ),
        branch_id=current_user.branch_id,
        branch=(
            MeBranch(id=branch.id, clinic_id=branch.clinic_id, name=branch.name)
            if branch is not None
            else None
        ),
        avatar_url=current_user.profile_photo,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
        updated_at=current_user.updated_at.isoformat(),
    )
