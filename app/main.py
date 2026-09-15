from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.rate_limit import limiter

from contextlib import asynccontextmanager
import asyncio
from app.services.moderation import process_moderation_queue

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: spawn moderation worker
    task = asyncio.create_task(process_moderation_queue())
    yield
    # Shutdown
    task.cancel()

app = FastAPI(
    title="Capstone API", 
    lifespan=lifespan,
    docs_url=None, # Disable default docs
    redoc_url=None,
    openapi_url=None,
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.api.routers import auth, recommend, chat
from app.api.dependencies import verify_api_key
from fastapi import Depends

# Configure CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    # Use regex to allow all origins dynamically so that credentials work
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply global API key check to all functional routers
app.include_router(auth.router, dependencies=[Depends(verify_api_key)])
app.include_router(recommend.router, dependencies=[Depends(verify_api_key)])
app.include_router(chat.router, dependencies=[Depends(verify_api_key)])

# Secure Docs with Basic Auth
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import HTTPException, status
import secrets
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from app.core.config import settings

security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    if not settings.DOCS_USERNAME or not settings.DOCS_PASSWORD:
        return credentials.username
    
    correct_username = secrets.compare_digest(credentials.username, settings.DOCS_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, settings.DOCS_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/docs", include_in_schema=False)
async def get_documentation(username: str = Depends(get_current_username)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

@app.get("/openapi.json", include_in_schema=False)
async def openapi(username: str = Depends(get_current_username)):
    return get_openapi(title="Capstone API", version="1.0.0", routes=app.routes)

@app.get("/", dependencies=[Depends(verify_api_key)])
def read_root():
    return {"status": "ok", "message": "Backend is running!"}

@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
