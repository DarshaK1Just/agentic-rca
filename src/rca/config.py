"""Central configuration — all runtime knobs read from the environment (BYOK).

Nothing here hardcodes a credential. `.env` is loaded once, lazily, so importing
this module never fails on a machine that has not configured keys yet (e.g. the
deterministic ingestion path and unit tests run with no LLM key at all).
"""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()  # no-op if .env is absent
except ImportError:
    # On Streamlit Cloud or other environments without python-dotenv,
    # environment variables are already set via the platform
    pass


@dataclass(frozen=True)
class Settings:
    # --- LLM provider selection ---------------------------------------------
    provider: str = os.getenv("RCA_LLM_PROVIDER", "gemini").lower()

    google_api_key: str | None = os.getenv("GOOGLE_API_KEY")
    gemini_model: str = os.getenv("RCA_GEMINI_MODEL", "gemini-2.5-flash")
    # If set, Gemini is reached via its OpenAI-compatible endpoint (Bearer key) instead
    # of the native google-generativeai SDK. Accepts either env var name.
    gemini_base_url: str | None = (
        os.getenv("RCA_GEMINI_BASE_URL") or os.getenv("GOOGLE_GEMINI_BASE_URL")
    )

    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openrouter_model: str = os.getenv("RCA_OPENROUTER_MODEL", "deepseek/deepseek-r1:free")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    ollama_base_url: str = os.getenv("RCA_OLLAMA_BASE_URL", "http://localhost:11434/v1")
    ollama_model: str = os.getenv("RCA_OLLAMA_MODEL", "llama3.1")

    # Fail fast on a slow/rate-limited LLM (seconds) so the engine reverts to its
    # deterministic narrative quickly instead of retrying with long backoff.
    llm_timeout: int = int(os.getenv("RCA_LLM_TIMEOUT", "20"))

    # --- Embeddings (local by default) --------------------------------------
    embed_model: str = os.getenv("RCA_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    # --- Agent retrieval budget (keeps us inside free-tier RPM/TPM) ---------
    max_agent_steps: int = int(os.getenv("RCA_MAX_AGENT_STEPS", "6"))
    max_evidence_rows: int = int(os.getenv("RCA_MAX_EVIDENCE_ROWS", "40"))
    # The heuristic planner is robust for these queries; default to it and spend the
    # single LLM call on synthesis only (gentler on free-tier rate limits). Set
    # RCA_LLM_PLANNER=1 to let the LLM also parse the query.
    use_llm_planner: bool = os.getenv("RCA_LLM_PLANNER", "0").lower() in ("1", "true", "yes")


settings = Settings()
