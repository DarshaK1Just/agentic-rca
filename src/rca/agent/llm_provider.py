"""Provider abstraction — one `get_chat_model()` entrypoint, BYOK from env.

The rest of the system never imports a vendor SDK directly; it asks for a model and
gets a LangChain chat model. Swapping Gemini ↔ OpenRouter ↔ local Ollama is a single
env var (`RCA_LLM_PROVIDER`). If no key is configured, `get_chat_model()` returns
None and the engine degrades to its deterministic report path — so the prototype is
always runnable, even offline / on a grader's machine with no keys.
"""
from __future__ import annotations

from rca.config import settings


def llm_available() -> bool:
    p = settings.provider
    if p == "gemini":
        return bool(settings.google_api_key)
    if p == "openrouter":
        return bool(settings.openrouter_api_key)
    if p == "ollama":
        return True  # assumed reachable locally; call will surface errors if not
    return False


def get_chat_model():
    """Return a LangChain chat model for the configured provider, or None."""
    p = settings.provider
    if p == "gemini" and settings.google_api_key:
        # Preferred: OpenAI-compatible endpoint (works with v1beta/openai/ keys and
        # avoids the deprecated google-generativeai SDK). Falls back to native SDK
        # only if no base URL is configured.
        if settings.gemini_base_url:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=settings.gemini_model,
                api_key=settings.google_api_key,
                base_url=settings.gemini_base_url,
                temperature=0, max_retries=0, timeout=settings.llm_timeout,
            )
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.google_api_key,
            temperature=0, max_retries=0, timeout=settings.llm_timeout,
        )
    if p == "openrouter" and settings.openrouter_api_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=0, max_retries=0, timeout=settings.llm_timeout,
        )
    if p == "ollama":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.ollama_model,
            api_key="ollama",  # placeholder; Ollama ignores it
            base_url=settings.ollama_base_url,
            temperature=0, max_retries=0, timeout=settings.llm_timeout,
        )
    return None
