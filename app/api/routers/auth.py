from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import get_db, get_current_user
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, Token
from app.core.security import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.studentEmail == user_data.studentEmail))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    new_user = User(
        studentEmail=user_data.studentEmail,
        passwordHash=get_password_hash(user_data.password)
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

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
    current_user.extractedAiTags = data.extractedAiTags
    current_user.isInternationalStudent = data.isInternationalStudent
    current_user.isFirstLogin = False
    
    db.add(current_user)
    await db.commit()
    
    return {"success": True}
