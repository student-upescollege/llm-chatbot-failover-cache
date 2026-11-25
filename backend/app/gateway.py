import os
import time
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from fastapi import HTTPException

logger = logging.getLogger("gateway")

class LLMGateway:
    def __init__(self, key_map: Dict[str, str], model: str, enable_simulation: bool):
        self.key_map = key_map # e.g. {"key_1": "...", "key_2": "..."}
        self.key_order = list(key_map.keys())
        self.model = model
        self.enable_simulation = enable_simulation
        # Exact response cache: cache_key -> dict(reply, input_tokens, output_tokens, model)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._litellm_module = None

    def _get_litellm(self):
        if self._litellm_module is None:
            try:
                import litellm
                litellm.telemetry = False
                litellm.drop_params = True
                try:
                    litellm.enable_cache(type="local")
                except Exception:
                    pass
                self._litellm_module = litellm
            except Exception as e:
                logger.warning(f"litellm not available: {e}")
        return self._litellm_module

    def compute_cache_key(self, model: str, messages: List[Dict[str, str]]) -> str:
        """
        Cache key: model + the full message list sent to the LLM
        (system prompt + history + new message).
        """
        payload = {
            "model": model,
            "messages": messages
        }
        raw_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def parse_simulation_header(self, header_val: Optional[str]) -> Dict[str, int]:
        """
        Parse X-Simulate-Failure header into a dictionary of {key_id: status_code}.
        Example: 'key_1=429,key_2=500' -> {'key_1': 429, 'key_2': 500}
        Example: '*=429' -> {'*': 429}
        """
        if not header_val or not self.enable_simulation:
            return {}
        rules = {}
        parts = [p.strip() for p in header_val.split(",") if p.strip()]
        for part in parts:
            if "=" in part:
                target, status_str = part.split("=", 1)
                try:
                    status_code = int(status_str.strip())
                    rules[target.strip()] = status_code
                except ValueError:
                    continue
        return rules

    def count_tokens(self, messages: List[Dict[str, str]], reply_text: str = "") -> Tuple[int, int]:
        """Estimate tokens for prompt and completion."""
        # Clean, fast deterministic token estimation
        total_prompt_chars = sum(len(m.get("content", "")) for m in messages)
        input_tokens = max(1, total_prompt_chars // 4)
        output_tokens = max(1, len(reply_text) // 4) if reply_text else 10
        return input_tokens, output_tokens

    async def execute_chat(
        self,
        messages: List[Dict[str, str]],
        simulate_failure_header: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main execution flow:
        1. Check Cache
        2. Key pool fallback loop (with simulation hooks)
        3. Store in Cache on success
        """
        start_time = time.perf_counter()

        # 1. Cache Check
        cache_key = self.compute_cache_key(self.model, messages)
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            return {
                "reply": cached_data["reply"],
                "metadata": {
                    "resolution_source": "LLM_CACHE",
                    "model": cached_data["model"],
                    "latency_ms": latency_ms,
                    "input_tokens": cached_data["input_tokens"],
                    "output_tokens": cached_data["output_tokens"],
                    "key_id": None,
                    "fallback_attempts": 0
                }
            }

        # 2. Key Pool and Auto-Fallback
        simulation_rules = self.parse_simulation_header(simulate_failure_header)
        fallback_attempts = 0
        last_error = None

        for key_id in self.key_order:
            api_key = self.key_map[key_id]

            # Check for simulated failure
            simulated_status = simulation_rules.get("*", simulation_rules.get(key_id))
            if simulated_status in (429, 500, 502, 503):
                logger.info(f"Simulating failure {simulated_status} for {key_id}")
                fallback_attempts += 1
                last_error = f"Simulated HTTP {simulated_status}"
                continue

            # Attempt live inference
            try:
                reply_text, input_tokens, output_tokens = await self._call_provider(api_key, messages)
                latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))

                # Store in cache
                self._cache[cache_key] = {
                    "reply": reply_text,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "model": self.model
                }

                return {
                    "reply": reply_text,
                    "metadata": {
                        "resolution_source": "LIVE_INFERENCE",
                        "model": self.model,
                        "latency_ms": latency_ms,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "key_id": key_id,
                        "fallback_attempts": fallback_attempts
                    }
                }
            except Exception as e:
                logger.warning(f"Key {key_id} failed: {e}")
                fallback_attempts += 1
                last_error = str(e)
                continue

        # If every key failed -> 503
        raise HTTPException(status_code=503, detail="all providers unavailable")

    async def _call_provider(
        self,
        api_key: str,
        messages: List[Dict[str, str]]
    ) -> Tuple[str, int, int]:
        """Perform provider call via LiteLLM or mock for dummy test keys."""
        # Check if dummy test key (for unit tests or local demo without live tokens)
        if api_key.startswith("dummy_") or api_key == "test_key":
            user_msg = messages[-1]["content"]
            if "capital of France" in user_msg:
                reply = "The capital of France is Paris."
            else:
                reply = f"I am your AI assistant. You said: '{user_msg}'"
            input_tokens, output_tokens = self.count_tokens(messages, reply)
            return reply, input_tokens, output_tokens

        # Real LiteLLM call
        litellm_mod = self._get_litellm()
        if not litellm_mod:
            raise RuntimeError("litellm is not installed or available")

        response = await litellm_mod.acompletion(
            model=self.model,
            messages=messages,
            api_key=api_key
        )
        reply = response.choices[0].message.content.strip()
        usage = getattr(response, "usage", None)
        if usage:
            input_tokens = getattr(usage, "prompt_tokens", 0)
            output_tokens = getattr(usage, "completion_tokens", 0)
        else:
            input_tokens, output_tokens = self.count_tokens(messages, reply)

        return reply, input_tokens, output_tokens
