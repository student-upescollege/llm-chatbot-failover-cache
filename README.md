# LLM Chatbot with Key Failover and Response Caching

A resilient, production-ready full-stack AI application demonstrating **automatic key failover across an LLM key pool**, **in-memory response caching**, and **multi-turn session storage backed by SQLite**.

Built with **React** (Frontend), **Python / FastAPI** (Backend), **LiteLLM**, and **SQLite**.

---

## 1. Live URLs

| Component | Status | URL |
| :--- | :--- | :--- |
| **GitHub Repository** | Public | `https://github.com/student-upescollege/llm-chatbot-failover-cache` |
| **Frontend UI** | Deployed | `https://llm-chatbot-failover-cache.vercel.app` *(or your Vercel URL)* |
| **Backend API** | Deployed | `https://llm-chatbot-failover-cache.onrender.com` *(or your Render URL)* |
| **Health Check** | Live | `https://llm-chatbot-failover-cache.onrender.com/health` |
| **Demo Video** | 2–3 min | `https://www.loom.com/share/...` *(Add your recording link)* |

---

## 2. Run Locally: With Docker and Without

### Option A: With Docker (Recommended)

Prerequisites: **Docker** and **Docker Compose** installed.

1. **Clone the repository and enter the directory**:
   ```bash
   git clone <your-repo-url>
   cd llm-chatbot-failover-cache
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env to supply your real API keys (e.g. Gemini, Groq, or OpenAI)
   ```

3. **Start the whole stack with a single command**:
   ```bash
   make up
   # Or: docker compose up --build -d
   ```
   - **Frontend UI**: [http://localhost:3000](http://localhost:3000)
   - **Backend API**: [http://localhost:8000](http://localhost:8000)
   - **API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Health Endpoint**: [http://localhost:8000/health](http://localhost:8000/health)

4. **Stop the stack**:
   ```bash
   make down
   # Or: docker compose down
   ```

---

### Option B: Without Docker (Local Development)

#### 1. Backend Setup
Prerequisites: **Python 3.10+**

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run backend tests
python -m pytest tests/test_api.py -v

# Start FastAPI server on port 8000
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Frontend Setup
Prerequisites: **Node.js 18+** and **npm**

```bash
cd frontend

# Install dependencies
npm install

# Start Vite dev server on port 3000
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 3. Design Decisions

### A. Key Fallback & Auto-Failover Pool
- **Gateway Architecture**: The backend maintains a deterministic ordered pool of keys (`key_1`, `key_2`, ...). When invoking LiteLLM, inference is attempted on `key_1`.
- **Automatic Failover**: If the provider returns HTTP 429 (rate limit), quota exhaustion, or any 5xx server error, the gateway catches the exception, increments `fallback_attempts`, and immediately retries the request using `key_2`.
- **Fault Isolation**: If every key in the pool fails, the server responds with a clean JSON `503 {"detail": "all providers unavailable"}` and **nothing is committed to the database**. The user never encounters an unhandled exception or broken UI.
- **Security**: The raw secret API keys are never leaked to the client; only the key identifier (`key_1`, `key_2`) is returned in response metadata.

### B. Response Caching
- **Exact Cache Key**: The cache key is formulated as:
  $$\text{SHA256}(\text{model} + \text{full message list [system prompt + history + new message]})$$
- **Cross-Session Hits**: If a user in a brand-new session asks the exact same initial query under the same system prompt, the request hits `LLM_CACHE` on the very first turn.
- **Cache Contract**: Cache hits return the identical reply text and original token counts, report `key_id = null`, `fallback_attempts = 0`, and execute with near-zero latency (`< 5ms`).
- **Safety**: A different question or subsequent turn with different conversational context never collides with the cache.

### C. SQLite Session Storage
- **Lightweight & Self-Contained**: Multi-turn history is stored directly in SQLite without third-party dependencies (no Redis or PostgreSQL required).
- **Restart Resilience**: When running in Docker, the database resides at `/data/app.db` backed by a Docker named volume (`sqlite_data`), ensuring session history survives container restarts and upgrades.
- **Atomicity**: Messages are recorded to SQLite only **after** successful inference, preventing corrupted or incomplete history on 503 or 422 errors.

---

## 4. Verification: How to See Failover, Cache Hits and Token Usage

### 1. Verification via the Web UI
1. **Live Inference**: Open [http://localhost:3000](http://localhost:3000). Type *"What is the capital of France?"* and press Enter. Notice the purple badge `LIVE_INFERENCE`, `key_1`, latency, and token metrics.
2. **Cache Hit**: Click **+ New Chat** (generating a fresh `session_id`). Send the same question: *"What is the capital of France?"*. Notice the green badge `LLM_CACHE`, `key_id: null`, and latency dropping to `1-2 ms`.
3. **Failover Simulation**: In the UI top panel, select `key_1=429` under **Simulate Failure** and send a new message. Notice that `key_1` fails over automatically to `key_2` (`key_id: key_2`, `Failed over: 1 key`).
4. **Provider Outage (503)**: Select `*=429` and send a message. Notice the clean error message displayed in chat without crashing the UI.

---

### 2. Verification via cURL Commands

#### A. Health Check
```bash
curl -X GET http://localhost:8000/health
```
**Expected Response (200)**:
```json
{
  "status": "ok",
  "keys_configured": 2,
  "cache_enabled": true
}
```

#### B. First Message (Live Inference)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "curl-s1", "message": "What is the capital of France?"}'
```
**Expected Response (200)**:
```json
{
  "session_id": "curl-s1",
  "reply": "The capital of France is Paris.",
  "metadata": {
    "resolution_source": "LIVE_INFERENCE",
    "model": "gemini/gemini-2.0-flash",
    "latency_ms": 780,
    "input_tokens": 18,
    "output_tokens": 7,
    "key_id": "key_1",
    "fallback_attempts": 0
  }
}
```

#### C. Identical First Message in New Session (Cache Hit)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "curl-s2", "message": "What is the capital of France?"}'
```
**Expected Response (200)**:
```json
{
  "session_id": "curl-s2",
  "reply": "The capital of France is Paris.",
  "metadata": {
    "resolution_source": "LLM_CACHE",
    "model": "gemini/gemini-2.0-flash",
    "latency_ms": 2,
    "input_tokens": 18,
    "output_tokens": 7,
    "key_id": null,
    "fallback_attempts": 0
  }
}
```

#### D. Failover Test Hook (`key_1=429`)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id": "curl-failover", "message": "Explain quantum computing briefly"}'
```
**Expected Response (200)**:
```json
{
  "session_id": "curl-failover",
  "reply": "...",
  "metadata": {
    "resolution_source": "LIVE_INFERENCE",
    "model": "gemini/gemini-2.0-flash",
    "key_id": "key_2",
    "fallback_attempts": 1
  }
}
```

#### E. Complete Provider Failure (`*=429`)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id": "curl-all-fail", "message": "Hello"}'
```
**Expected Response (503)**:
```json
{
  "detail": "all providers unavailable"
}
```

#### F. Session History Retrieval
```bash
curl -X GET http://localhost:8000/sessions/curl-s1/messages
```

---

## 5. Setup Used: Editor and AI Tools

- **IDE / Editor**: Visual Studio Code
- **AI Coding Assistants**: Google Antigravity (Gemini 3.8 Flash High) for rapid architecture validation, edge-case analysis, and end-to-end testing.
- **Runtimes & Frameworks**:
  - Python 3.11/3.14 with FastAPI and Uvicorn
  - Node.js 20 with React 18 and Vite
  - Docker 29 and Docker Compose
  - SQLite 3

---

## 6. Bonus Features

1. **Interactive Failover Simulator in UI**: In addition to cURL header testing, the frontend features an on-screen dropdown to simulate `key_1=429`, `key_1=500`, and `*=429` live without leaving the browser.
2. **Visual Cache & Latency Badges**: Each assistant reply includes color-coded badges highlighting cache hits in green (`LLM_CACHE`) and live calls in purple (`LIVE_INFERENCE`), accompanied by real millisecond timings.
3. **Session Switcher & Reset**: A dedicated "+ New Chat" action instantly provisions a fresh session ID while keeping past SQLite session logs intact for auditing.
4. **Full Automated Test Suite**: Built-in pytest suite (`backend/tests/test_api.py`) covering health checks, multi-turn dialogue, cache consistency, key failover hooks, 422 validations, and 404 session handling.

