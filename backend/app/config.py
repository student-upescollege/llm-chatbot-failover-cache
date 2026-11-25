import os
from typing import List, Dict
from dotenv import load_dotenv

# Disable remote cost map fetch and telemetry for speed and offline resilience
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["LITELLM_LOG"] = "ERROR"

load_dotenv()

class Settings:
    def __init__(self):
        # Comma-separated key pool, at least 2 keys. Key ids are key_1, key_2, ... in this order.
        keys_str = os.getenv("LLM_API_KEYS", "dummy_key_1,dummy_key_2")
        self.api_keys: List[str] = [k.strip() for k in keys_str.split(",") if k.strip()]
        if len(self.api_keys) < 2:
            self.api_keys = ["dummy_key_1", "dummy_key_2"]

        self.key_map: Dict[str, str] = {f"key_{i+1}": key for i, key in enumerate(self.api_keys)}

        # Default model: gemini/gemini-2.0-flash or groq/llama-3.1-8b-instant or gpt-4o-mini
        self.model: str = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")

        # Database URL
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

        # CORS Allowed Origins
        origins_str = os.getenv("ALLOWED_ORIGINS", "*")
        self.allowed_origins: List[str] = [o.strip() for o in origins_str.split(",") if o.strip()]

        # Failure simulation switch (must be true on deployed backend)
        self.enable_failure_simulation: bool = os.getenv("ENABLE_FAILURE_SIMULATION", "true").strip().lower() in ("true", "1", "yes")

        # Optional default system prompt
        self.default_system_prompt: str = os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful and concise AI assistant.")

settings = Settings()
