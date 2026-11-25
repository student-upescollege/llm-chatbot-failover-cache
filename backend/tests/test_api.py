import os
import time
import pytest
import httpx
from app.main import app, db, gateway

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Use an isolated SQLite database and fresh gateway cache for each test."""
    test_db_path = str(tmp_path / f"test_{int(time.time() * 1000)}.db")
    db.db_path = test_db_path
    db.init_db()
    gateway._cache.clear()
    gateway.enable_simulation = True
    yield
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except OSError:
            pass

@pytest.mark.asyncio
async def test_health_endpoint():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["keys_configured"] >= 2
        assert data["cache_enabled"] is True

@pytest.mark.asyncio
async def test_chat_live_inference():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "session_id": "test-s1",
            "message": "What is the capital of France?"
        }
        response = await ac.post("/chat", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-s1"
        assert "Paris" in data["reply"]
        assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"
        assert data["metadata"]["key_id"] == "key_1"
        assert data["metadata"]["fallback_attempts"] == 0
        assert data["metadata"]["input_tokens"] > 0
        assert data["metadata"]["output_tokens"] > 0
        assert isinstance(data["metadata"]["latency_ms"], int)

@pytest.mark.asyncio
async def test_chat_caching_behavior():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # First request in session 1 -> LIVE_INFERENCE
        res1 = await ac.post("/chat", json={"session_id": "session-A", "message": "What is the capital of France?"})
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["metadata"]["resolution_source"] == "LIVE_INFERENCE"

        # Same first message in a NEW session -> MUST hit LLM_CACHE
        res2 = await ac.post("/chat", json={"session_id": "session-B", "message": "What is the capital of France?"})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["metadata"]["resolution_source"] == "LLM_CACHE"
        assert data2["reply"] == data1["reply"]
        assert data2["metadata"]["key_id"] is None
        assert data2["metadata"]["fallback_attempts"] == 0
        assert data2["metadata"]["input_tokens"] == data1["metadata"]["input_tokens"]
        assert data2["metadata"]["output_tokens"] == data1["metadata"]["output_tokens"]

        # Different message in session C -> LIVE_INFERENCE
        res3 = await ac.post("/chat", json={"session_id": "session-C", "message": "What is the capital of Japan?"})
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["metadata"]["resolution_source"] == "LIVE_INFERENCE"

@pytest.mark.asyncio
async def test_key_failover_hook():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. key_1=429 should fail over to key_2
        res1 = await ac.post(
            "/chat",
            json={"session_id": "failover-s1", "message": "Tell me a joke"},
            headers={"X-Simulate-Failure": "key_1=429"}
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["metadata"]["key_id"] == "key_2"
        assert data1["metadata"]["fallback_attempts"] == 1
        assert data1["metadata"]["resolution_source"] == "LIVE_INFERENCE"

        # 2. key_1=500 should fail over to key_2
        gateway._cache.clear()
        res2 = await ac.post(
            "/chat",
            json={"session_id": "failover-s2", "message": "Tell me a story"},
            headers={"X-Simulate-Failure": "key_1=500"}
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["metadata"]["key_id"] == "key_2"
        assert data2["metadata"]["fallback_attempts"] == 1

        # 3. *=429 means every key fails -> 503
        gateway._cache.clear()
        res3 = await ac.post(
            "/chat",
            json={"session_id": "failover-s3", "message": "Hello world"},
            headers={"X-Simulate-Failure": "*=429"}
        )
        assert res3.status_code == 503
        assert res3.json() == {"detail": "all providers unavailable"}

        # Verify nothing was added to history for the failed session
        hist_res = await ac.get("/sessions/failover-s3/messages")
        assert hist_res.status_code == 404
        assert hist_res.json() == {"detail": "session not found"}

@pytest.mark.asyncio
async def test_multi_turn_history():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        sid = "multi-turn-session"
        # Turn 1
        res1 = await ac.post("/chat", json={"session_id": sid, "message": "Hi, I am Alice"})
        assert res1.status_code == 200

        # Turn 2
        res2 = await ac.post("/chat", json={"session_id": sid, "message": "What is my name?"})
        assert res2.status_code == 200

        # Retrieve history
        res = await ac.get(f"/sessions/{sid}/messages")
        assert res.status_code == 200
        history = res.json()
        assert history["session_id"] == sid
        messages = history["messages"]
        assert len(messages) == 4
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hi, I am Alice"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["metadata"]["resolution_source"] in ("LIVE_INFERENCE", "LLM_CACHE")
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "What is my name?"
        assert messages[3]["role"] == "assistant"

@pytest.mark.asyncio
async def test_validation_errors_422():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # Empty message
        res1 = await ac.post("/chat", json={"session_id": "s1", "message": "   "})
        assert res1.status_code == 422
        assert "detail" in res1.json()

        # Missing message
        res2 = await ac.post("/chat", json={"session_id": "s1"})
        assert res2.status_code == 422

        # Missing session_id
        res3 = await ac.post("/chat", json={"message": "hello"})
        assert res3.status_code == 422

        # Message over 4000 characters
        res4 = await ac.post("/chat", json={"session_id": "s1", "message": "A" * 4001})
        assert res4.status_code == 422

@pytest.mark.asyncio
async def test_unknown_session_404():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/sessions/nonexistent-session-id-12345/messages")
        assert res.status_code == 404
        assert res.json() == {"detail": "session not found"}
