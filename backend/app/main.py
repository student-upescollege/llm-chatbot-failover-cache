import os
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .config import settings
from .database import Database, resolve_db_path
from .gateway import LLMGateway
from .schemas import (
    HealthResponse,
    ChatRequest,
    ChatResponse,
    ChatMetadata,
    SessionMessagesResponse,
    SessionMessage
)

db_path = resolve_db_path(settings.database_url)
db = Database(db_path)
gateway = LLMGateway(
    key_map=settings.key_map,
    model=settings.model,
    enable_simulation=settings.enable_failure_simulation
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema on startup
    db.init_db()
    yield

app = FastAPI(
    title="LLM Chatbot Gateway",
    description="LLM Chatbot with Key Failover, Response Caching, and SQLite Session Storage",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins if settings.allowed_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers to guarantee strictly JSON with "detail" field
from fastapi.encoders import jsonable_encoder

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors())}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal server error"}
    )

@app.get("/health", response_model=HealthResponse)
def health():
    """
    Returns 200 once app is running, DB is reachable, and key pool is loaded.
    { "status": "ok", "keys_configured": 2, "cache_enabled": true }
    """
    return HealthResponse(
        status="ok",
        keys_configured=len(settings.api_keys),
        cache_enabled=True
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure")
):
    """
    Main chat endpoint with key failover, response caching, and multi-turn state.
    """
    session_id = payload.session_id
    user_message = payload.message.strip()
    system_prompt = payload.system_prompt if payload.system_prompt else settings.default_system_prompt

    # 1. Fetch prior history from SQLite
    history_messages = db.get_session_messages(session_id) or []

    # 2. Build full message list sent to LLM:
    # [system_prompt] + history + [new user message]
    llm_messages = [{"role": "system", "content": system_prompt}]
    for h in history_messages:
        llm_messages.append({"role": h["role"], "content": h["content"]})
    llm_messages.append({"role": "user", "content": user_message})

    # 3. Execute via Gateway (Cache lookup -> Failover key pool)
    # If this raises 503, nothing is committed to the database!
    result = await gateway.execute_chat(
        messages=llm_messages,
        simulate_failure_header=x_simulate_failure
    )

    reply_text = result["reply"]
    meta_dict = result["metadata"]

    # 4. Save to SQLite session history ONLY after inference succeeds
    db.add_message(session_id=session_id, role="user", content=user_message, metadata=None)
    db.add_message(
        session_id=session_id,
        role="assistant",
        content=reply_text,
        metadata={
            "resolution_source": meta_dict["resolution_source"],
            "input_tokens": meta_dict["input_tokens"],
            "output_tokens": meta_dict["output_tokens"],
            "model": meta_dict["model"],
            "latency_ms": meta_dict["latency_ms"],
            "key_id": meta_dict["key_id"],
            "fallback_attempts": meta_dict["fallback_attempts"]
        }
    )

    return ChatResponse(
        session_id=session_id,
        reply=reply_text,
        metadata=ChatMetadata(**meta_dict)
    )

@app.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
def get_session_history(session_id: str):
    """
    Returns stored history of one session from SQLite, oldest first, without the system prompt.
    If session is unknown, returns 404 {"detail": "session not found"}.
    """
    messages = db.get_session_messages(session_id)
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="session not found"
        )

    session_messages = [
        SessionMessage(
            role=m["role"],
            content=m["content"],
            metadata=m.get("metadata")
        )
        for m in messages
    ]

    return SessionMessagesResponse(
        session_id=session_id,
        messages=session_messages
    )
