from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
import uuid
from datetime import datetime, timezone, timedelta

from app.api.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.token import VerificationToken
from app.schemas.user import UserCreate, UserResponse, Token
from app.core.security import get_password_hash, verify_password, create_access_token, create_password_reset_token, verify_password_reset_token
from app.services.llm_service import extract_tags_from_bio
from pydantic import BaseModel, EmailStr
import httpx
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.studentEmail == user_data.studentEmail))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    new_user = User(
        studentEmail=user_data.studentEmail,
        passwordHash=get_password_hash(user_data.password),
        isVerified=False
    )
    db.add(new_user)
    
    # Generate Verification Token
    token_str = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    v_token = VerificationToken(
        email=user_data.studentEmail,
        token=token_str,
        expiresAt=expires_at
    )
    db.add(v_token)
    
    await db.commit()
    await db.refresh(new_user)
    
    # Send email
    if settings.RESEND_API_KEY:
        base_url = str(request.base_url).rstrip('/')
        confirm_link = f"{base_url}/api/auth/verify?token={token_str}"
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": "Capestone Project <onboarding@invertaxis.com>",
                    "to": [user_data.studentEmail],
                    "subject": "Verify your email address",
                    "html": f"""
                        <div style="font-family: sans-serif; max-w: 600px; margin: 0 auto;">
                          <h2>Welcome!</h2>
                          <p>Please confirm your email address by clicking the link below. This link will expire in 24 hours.</p>
                          <div style="margin: 30px 0;">
                            <a href="{confirm_link}" style="background-color: #363636; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                              Verify Email Address
                            </a>
                          </div>
                        </div>
                    """
                }
            )
            
    return new_user

@router.get("/verify")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(VerificationToken).where(VerificationToken.token == token))
    v_token = result.scalars().first()
    
    if not v_token:
        raise HTTPException(status_code=400, detail="Invalid verification token")
        
    # Make expiresAt naive for comparison if DB returns naive, but Postgres usually handles timezone=True
    now_utc = datetime.now(timezone.utc)
    if getattr(v_token.expiresAt, "tzinfo", None) is None:
        now_utc = datetime.utcnow()
        
    if v_token.expiresAt < now_utc:
        raise HTTPException(status_code=400, detail="Verification token expired")
        
    user_res = await db.execute(select(User).where(User.studentEmail == v_token.email))
    user = user_res.scalars().first()
    
    if user:
        user.isVerified = True
        user.lastVerifiedAt = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(user)
        
    await db.delete(v_token)
    await db.commit()
    
    return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?verified=true")

class ResendVerificationRequest(BaseModel):
    email: EmailStr

@router.post("/resend-verification")
async def resend_verification(req: ResendVerificationRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.studentEmail == req.email))
    user = result.scalars().first()
    
    if not user or user.isVerified:
        return {"message": "If an unverified account with that email exists, we have resent the confirmation link."}
        
    # Delete existing tokens
    existing = await db.execute(select(VerificationToken).where(VerificationToken.email == req.email))
    for t in existing.scalars().all():
        await db.delete(t)
        
    # Generate new token
    token_str = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    v_token = VerificationToken(email=req.email, token=token_str, expiresAt=expires_at)
    db.add(v_token)
    await db.commit()
    
    if settings.RESEND_API_KEY:
        base_url = str(request.base_url).rstrip('/')
        confirm_link = f"{base_url}/api/auth/verify?token={token_str}"
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": "Capestone Project <onboarding@invertaxis.com>",
                    "to": [req.email],
                    "subject": "Verify your email address",
                    "html": f"<p>Please click this link to verify your email: <a href='{confirm_link}'>{confirm_link}</a></p>"
                }
            )
            
    return {"message": "Verification email resent"}



@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.studentEmail == form_data.username))
    user = result.scalars().first()
    
    if not user or not verify_password(form_data.password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

from app.schemas.onboard import UserOnboard

@router.post("/onboard")
async def onboard_user(
    data: UserOnboard,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_user.displayName = data.displayName
    current_user.age = data.age
    current_user.university = data.university
    current_user.yearOfStudy = data.yearOfStudy
    current_user.isFirstTimeUni = (data.yearOfStudy == 1)
    current_user.languages = data.languages
    current_user.introvertExtrovertScore = data.introvertExtrovertScore
    current_user.socialEnergyLevel = data.socialEnergyLevel
    current_user.lookingForTags = data.lookingForTags
    current_user.bio = data.bio
    current_user.isInternationalStudent = data.isInternationalStudent
    current_user.isFirstLogin = False
    
    if data.bio and len(data.bio) >= 10:
        extracted_tags = await extract_tags_from_bio(data.bio)
        current_user.extractedAiTags = extracted_tags
    elif data.extractedAiTags:
        current_user.extractedAiTags = data.extractedAiTags
    
    db.add(current_user)
    await db.commit()
    
    return {"success": True}

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

@router.post("/reset-password-request")
async def reset_password_request(req: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.studentEmail == req.email))
    user = result.scalars().first()
    
    if not user:
        # Prevent email enumeration by returning a generic success message
        return {"message": "If an account with that email exists, we have sent a reset link."}
        
    token = create_password_reset_token(email=req.email)
    
    origin = settings.FRONTEND_URL
    reset_link = f"{origin}/reset-password?token={token}"
    
    if settings.RESEND_API_KEY:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": "Capestone Project <onboarding@invertaxis.com>",
                    "to": [req.email],
                    "subject": "Reset your password",
                    "html": f"""
                        <div style="font-family: sans-serif; max-w: 600px; margin: 0 auto;">
                          <h2>Password Reset Request</h2>
                          <p>We received a request to reset your password. Click the link below to choose a new one. This link will expire in 15 minutes.</p>
                          <a href="{reset_link}" style="display: inline-block; padding: 12px 24px; background-color: #444444; color: white; text-decoration: none; border-radius: 6px; margin-top: 16px;">Reset Password</a>
                          <p style="margin-top: 24px; font-size: 14px; color: #666;">If you didn't request this, you can safely ignore this email.</p>
                          <hr style="border: none; border-top: 1px solid #eaeaea; margin-top: 30px;" />
                          <p style="color: #999; font-size: 12px;">Or copy and paste this link into your browser: <br/> {reset_link}</p>
                        </div>
                    """
                }
            )
            res_body = res.text
            try:
                res_body = res.json()
            except:
                pass
            return {"message": "Reset request processed", "resend_status": res.status_code, "resend_response": res_body}
            
    return {"message": "If an account with that email exists, we have sent a reset link.", "resend_status": "No API Key"}

@router.post("/reset-password")
async def reset_password(req: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    email = verify_password_reset_token(req.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        
    result = await db.execute(select(User).where(User.studentEmail == email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if verify_password(req.new_password, user.passwordHash):
        raise HTTPException(status_code=400, detail="Your new password must be different from your previously used one.")
        
    user.passwordHash = get_password_hash(req.new_password)
    db.add(user)
    await db.commit()
    
    return {"message": "Password successfully reset"}
