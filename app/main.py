from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.rate_limit import limiter

app = FastAPI(title="Capstone API")

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.api.routers import auth, recommend, chat

# Configure CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    # Use regex to allow all origins dynamically so that credentials work
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(recommend.router)
app.include_router(chat.router)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Backend is running!"}

@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
