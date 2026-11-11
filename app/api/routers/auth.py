from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
import uuid
from datetime import datetime, timezone, timedelta

from app.api.dependencies import get_db, get_current_user
from app.db.session import async_session
from app.models.user import User
from app.models.token import VerificationToken
from app.schemas.user import UserCreate, UserResponse, Token, UserProfileUpdate
from app.core.security import get_password_hash, verify_password, create_access_token, create_password_reset_token, verify_password_reset_token
from app.services.llm_service import extract_tags_from_bio, generate_user_embedding
from app.services.recommender import pregenerate_user_rationales
from pydantic import BaseModel, EmailStr
import httpx
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

async def _bg_pregenerate_user_rationales(user_id: str):
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            if user:
                await pregenerate_user_rationales(session, user)
    except Exception as e:
        print(f"Error in background rationale pregeneration for user {user_id}: {e}")


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
    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
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
        origin = request.headers.get("origin") or settings.FRONTEND_URL
        confirm_link = f"{origin}/api/auth/verify?token={token_str}"
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
                          <p>Please confirm your email address by clicking the link below. This link will expire in 2 hours.</p>
                          <div style="margin: 30px 0;">
                            <a href="{confirm_link}" style="background-color: #363636; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                              Verify Email Address
                            </a>
                          </div>
                          <hr style="border: none; border-top: 1px solid #eaeaea; margin-top: 30px;" />
                          <p style="color: #999; font-size: 12px;">Or copy and paste this link into your browser: <br/> {confirm_link}</p>
                        </div>
                    """,
                    "text": f"Welcome!\n\nPlease confirm your email address by clicking the link below:\n{confirm_link}\n\nThis link will expire in 2 hours."
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
        
    # Generate new token (tokens expire naturally via expiresAt)
    token_str = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    v_token = VerificationToken(email=req.email, token=token_str, expiresAt=expires_at)
    db.add(v_token)
    await db.commit()
    
    if settings.RESEND_API_KEY:
        origin = request.headers.get("origin") or settings.FRONTEND_URL
        confirm_link = f"{origin}/api/auth/verify?token={token_str}"
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": "Capestone Project <onboarding@invertaxis.com>",
                    "to": [req.email],
                    "subject": "Verify your email address",
                    "html": f"""
                        <div style="font-family: sans-serif; max-w: 600px; margin: 0 auto;">
                          <h2>Confirm your Email Address</h2>
                          <p>Here is your new verification link. This link will expire in 2 hours.</p>
                          <div style="margin: 30px 0;">
                            <a href="{confirm_link}" style="background-color: #363636; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                              Verify Email Address
                            </a>
                          </div>
                          <hr style="border: none; border-top: 1px solid #eaeaea; margin-top: 30px;" />
                          <p style="color: #999; font-size: 12px;">Or copy and paste this link into your browser: <br/> {confirm_link}</p>
                        </div>
                    """,
                    "text": f"Confirm your Email Address\n\nPlease click this link to verify your email:\n{confirm_link}\n\nThis link will expire in 2 hours."
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
        
    if not user.isVerified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before logging in.",
        )
        
    access_token = create_access_token(subject=user.id)
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "isFirstLogin": user.isFirstLogin
    }

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

from app.schemas.onboard import UserOnboard

@router.post("/onboard")
async def onboard_user(
    data: UserOnboard,
    background_tasks: BackgroundTasks,
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
    current_user.interests = data.lookingForTags
    current_user.bio = data.bio
    current_user.isInternationalStudent = data.isInternationalStudent
    current_user.isFirstLogin = False
    
    if data.extractedAiTags:
        current_user.extractedAiTags = data.extractedAiTags
    elif data.bio and len(data.bio) >= 10:
        try:
            extracted_tags = await extract_tags_from_bio(data.bio)
            current_user.extractedAiTags = extracted_tags
        except Exception as e:
            print(f"Error extracting tags in onboarding: {e}")
    
    try:
        new_embedding = await generate_user_embedding({
            "bio": current_user.bio,
            "interests": current_user.interests,
            "lookingForTags": current_user.lookingForTags,
            "languages": current_user.languages
        })
        if new_embedding:
            current_user.cachedVectorEmbedding = new_embedding
    except Exception as e:
        print(f"Error generating initial user vector embedding: {e}")

    db.add(current_user)
    await db.commit()

    background_tasks.add_task(_bg_pregenerate_user_rationales, current_user.id)
    
    return {"success": True}

@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    data: UserProfileUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Detect what actually changed before updating fields
    bio_changed = (data.bio is not None and data.bio.strip() != (current_user.bio or "").strip())
    interests_changed = (data.interests is not None and set(data.interests) != set(current_user.interests or []))
    languages_changed = (data.languages is not None and set(data.languages) != set(current_user.languages or []))
    energy_changed = (data.socialEnergyLevel is not None and data.socialEnergyLevel != current_user.socialEnergyLevel)
    score_changed = (data.introvertExtrovertScore is not None and data.introvertExtrovertScore != current_user.introvertExtrovertScore)

    rec_fields_changed = bio_changed or interests_changed or languages_changed or energy_changed or score_changed

    if data.displayName is not None:
        current_user.displayName = data.displayName
    if data.languages is not None:
        current_user.languages = data.languages
    if data.introvertExtrovertScore is not None:
        current_user.introvertExtrovertScore = data.introvertExtrovertScore
    if data.socialEnergyLevel is not None:
        current_user.socialEnergyLevel = data.socialEnergyLevel
    if data.interests is not None:
        current_user.interests = data.interests
        current_user.lookingForTags = data.interests
    if data.bio is not None:
        current_user.bio = data.bio

    # AI Tag Extraction: use client-provided tags if available, else extract if bio changed
    if data.extractedAiTags is not None:
        current_user.extractedAiTags = data.extractedAiTags
    elif bio_changed and data.bio and len(data.bio.strip()) >= 10:
        try:
            extracted_tags = await extract_tags_from_bio(data.bio.strip())
            if extracted_tags:
                current_user.extractedAiTags = extracted_tags
        except Exception as e:
            print(f"Error extracting tags from bio: {e}")

    # Vector Embedding: ONLY re-generate if semantic matching fields (bio, interests, languages) changed
    if bio_changed or interests_changed or languages_changed:
        try:
            new_embedding = await generate_user_embedding({
                "bio": current_user.bio,
                "interests": current_user.interests,
                "lookingForTags": current_user.lookingForTags,
                "languages": current_user.languages
            })
            if new_embedding:
                current_user.cachedVectorEmbedding = new_embedding
            else:
                current_user.cachedVectorEmbedding = []
        except Exception as e:
            print(f"Error updating user vector embedding: {e}")
            current_user.cachedVectorEmbedding = []

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    # Pre-generate rationales in the background: ONLY if recommendation-driving fields changed
    if rec_fields_changed:
        background_tasks.add_task(_bg_pregenerate_user_rationales, current_user.id)

    return current_user


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
    
    # Use the origin header to support Vercel preview deployments dynamically.
    # Fallback to the environment variable if the origin header is missing.
    origin = request.headers.get("origin") or settings.FRONTEND_URL

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
