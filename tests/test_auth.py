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
    TC-002: Click an email verification link that was generated more than 24 hours ago.
    Expected: The verification fails. System returns an "Expired Token" error.
    """
    from tests.conftest import TestingSessionLocal
    
    # Manually create a user and an expired token in the test db
    async with TestingSessionLocal() as session:
        user = User(studentEmail="testuser@cput.ac.za", passwordHash="hashed", isVerified=False)
        session.add(user)
        
        token_str = str(uuid.uuid4())
        # Set expiration to 25 hours ago
        expired_time = datetime.now(timezone.utc) - timedelta(hours=25)
        
        v_token = VerificationToken(email="testuser@cput.ac.za", token=token_str, expiresAt=expired_time)
        session.add(v_token)
        await session.commit()
        
    response = await async_client.get(f"/api/auth/verify?token={token_str}")
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Verification token expired"
