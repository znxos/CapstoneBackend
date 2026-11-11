import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel import select
from app.models.user import User
from app.models.token import VerificationToken
import uuid
from datetime import datetime, timezone, timedelta
from app.db.session import get_db

@pytest.mark.asyncio
async def test_tc001_email_domain_validation(async_client: AsyncClient):
    """
    TC-001: Attempt to sign up using a non-university email address (e.g., @gmail.com).
    Expected: Registration is blocked. System displays an error requiring an .ac.za domain.
    """
    response = await async_client.post(
        "/api/auth/signup",
        json={"studentEmail": "testuser@gmail.com", "password": "SecurePassword123!"}
    )
    
    assert response.status_code == 422
    assert "Email must belong to one of the stipulated universities" in response.text

@pytest.mark.asyncio
async def test_tc002_verification_token_expiry(async_client: AsyncClient, setup_db):
    """
    TC-002: Click an email verification link that was generated more than 2 hours ago.
    Expected: The verification fails. System returns an "Expired Token" error.
    """
    from tests.conftest import TestingSessionLocal
    
    # Manually create a user and an expired token in the test db
    async with TestingSessionLocal() as session:
        user = User(studentEmail="testuser@cput.ac.za", passwordHash="hashed", isVerified=False)
        session.add(user)
        
        token_str = str(uuid.uuid4())
        # Set expiration to 3 hours ago (past the 2-hour window)
        expired_time = datetime.now(timezone.utc) - timedelta(hours=3)
        
        v_token = VerificationToken(email="testuser@cput.ac.za", token=token_str, expiresAt=expired_time)
        session.add(v_token)
        await session.commit()
        
    response = await async_client.get(f"/api/auth/verify?token={token_str}")
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Verification token expired"

@pytest.mark.asyncio
async def test_verification_token_not_deleted_on_verify(async_client: AsyncClient, setup_db):
    """
    Ensure the verification token is retained in the database after successful verification,
    relying on expiresAt rather than deletion.
    """
    from tests.conftest import TestingSessionLocal
    
    token_str = str(uuid.uuid4())
    future_time = datetime.now(timezone.utc) + timedelta(hours=2)
    
    async with TestingSessionLocal() as session:
        user = User(studentEmail="persist_token@mycput.ac.za", passwordHash="hashed", isVerified=False)
        session.add(user)
        v_token = VerificationToken(email="persist_token@mycput.ac.za", token=token_str, expiresAt=future_time)
        session.add(v_token)
        await session.commit()
        
    # Verify the email
    response = await async_client.get(f"/api/auth/verify?token={token_str}", follow_redirects=False)
    assert response.status_code == 307 or response.status_code == 302
    
    # Check that user is verified AND token still exists in DB
    async with TestingSessionLocal() as session:
        user_res = await session.execute(select(User).where(User.studentEmail == "persist_token@mycput.ac.za"))
        assert user_res.scalars().first().isVerified is True
        
        token_res = await session.execute(select(VerificationToken).where(VerificationToken.token == token_str))
        token_in_db = token_res.scalars().first()
        assert token_in_db is not None
        assert token_in_db.token == token_str

@pytest.mark.asyncio
async def test_unverified_user_cannot_login(async_client: AsyncClient, setup_db):
    """
    Attempt to log in with valid credentials while unverified.
    Expected: HTTP 403 Forbidden with prompt to verify email.
    """
    from tests.conftest import TestingSessionLocal
    from app.core.security import get_password_hash
    
    async with TestingSessionLocal() as session:
        user = User(
            studentEmail="unverified@mycput.ac.za",
            passwordHash=get_password_hash("ValidPassword123!"),
            isVerified=False
        )
        session.add(user)
        await session.commit()
        
    response = await async_client.post(
        "/api/auth/login",
        data={"username": "unverified@mycput.ac.za", "password": "ValidPassword123!"}
    )
    
    assert response.status_code == 403
    assert response.json()["detail"] == "Please verify your email address before logging in."

@pytest.mark.asyncio
async def test_verified_user_can_login(async_client: AsyncClient, setup_db):
    """
    Attempt to log in with valid credentials after email is verified.
    Expected: HTTP 200 OK with access token.
    """
    from tests.conftest import TestingSessionLocal
    from app.core.security import get_password_hash
    
    async with TestingSessionLocal() as session:
        user = User(
            studentEmail="verified@mycput.ac.za",
            passwordHash=get_password_hash("ValidPassword123!"),
            isVerified=True
        )
        session.add(user)
        await session.commit()
        
    response = await async_client.post(
        "/api/auth/login",
        data={"username": "verified@mycput.ac.za", "password": "ValidPassword123!"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["isFirstLogin"] is True
