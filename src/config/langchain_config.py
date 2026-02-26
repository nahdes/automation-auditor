"""
src/config/langchain_config.py
──────────────────────────────
LangChain configuration with Groq, Ollama, and cloud provider support.
Uses lazy imports to avoid ImportError when optional dependencies are missing.
"""
import os
import logging
from typing import Optional, TYPE_CHECKING
from langchain_core.language_models import BaseChatModel
from dotenv import load_dotenv
# Load .env at module import time (works for tests + main app)
load_dotenv(override=True)   # override=True so it always wins over system env

logger = logging.getLogger(__name__)

# Type checking only - avoids runtime import errors
if TYPE_CHECKING:
    from langchain_groq import ChatGroq
    from langchain_ollama import ChatOllama
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic

logger = logging.getLogger(__name__)


def get_llm(
    provider: str = "groq",
    model_name: Optional[str] = None,
    temperature: float = 0.3,
    **kwargs
) -> BaseChatModel:
    """
    Factory function to get LLM based on provider.
    
    Priority: Groq → Ollama → OpenAI → Anthropic
    
    Args:
        provider: "groq", "ollama", "openai", or "anthropic"
        model_name: Specific model name (uses config default if None)
        temperature: Model temperature for sampling
        **kwargs: Additional model arguments
    
    Returns:
        Configured LangChain ChatModel instance
    """
    if provider == "groq":
        return _get_groq(model_name, temperature, **kwargs)
    elif provider == "ollama":
        return _get_ollama(model_name, temperature, **kwargs)
    elif provider == "openai":
        return _get_openai(model_name, temperature, **kwargs)
    elif provider == "anthropic":
        return _get_anthropic(model_name, temperature, **kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _get_groq(
    model_name: Optional[str],
    temperature: float,
    **kwargs
) -> BaseChatModel:
    """Get Groq chat model with lazy import. FIXED: No base_url duplication."""
    try:
        from langchain_groq import ChatGroq
    except ImportError as exc:
        logger.error("langchain-groq not installed. Run: pip install langchain-groq")
        raise ImportError(
            "Groq support requires 'langchain-groq'. "
            "Install with: pip install langchain-groq"
        ) from exc
    
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY not set in environment. "
            "Get key from https://console.groq.com and add to .env"
        )
    
    model = model_name or os.getenv("GROQ_MODEL", "llama3-8b-8192")
    
    logger.info("🚀 Initializing Groq: %s", model)
    
    # ✅ FIXED: ChatGroq has base_url built-in. Do NOT pass base_url parameter.
    return ChatGroq(
        model=model,
        temperature=temperature,
        api_key=api_key,
        timeout=kwargs.get("timeout", 60),
        max_retries=kwargs.get("max_retries", 2),
        # Remove any base_url parameter - it causes URL duplication!
        **{k: v for k, v in kwargs.items() if k not in [
            "model", "temperature", "api_key", "timeout", "max_retries", "base_url"
        ]}
    )

def _get_ollama(
    model_name: Optional[str],
    temperature: float,
    **kwargs
) -> BaseChatModel:
    """Get Ollama chat model with lazy import."""
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        logger.error("langchain-ollama not installed. Run: pip install langchain-ollama")
        raise ImportError(
            "Ollama support requires 'langchain-ollama'. "
            "Install with: pip install langchain-ollama"
        ) from exc
    
    model = model_name or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    logger.info("🦙 Initializing Ollama: %s @ %s", model, base_url)
    
    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        num_predict=kwargs.get("num_predict", 2048),
        num_ctx=kwargs.get("num_ctx", 4096),
        timeout=kwargs.get("timeout", 300),
    )


def _get_openai(
    model_name: Optional[str],
    temperature: float,
    **kwargs
) -> BaseChatModel:
    """Get OpenAI chat model with lazy import."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        logger.error("langchain-openai not installed. Run: pip install langchain-openai")
        raise ImportError(
            "OpenAI support requires 'langchain-openai'. "
            "Install with: pip install langchain-openai"
        ) from exc
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY not set in environment")
    
    model = model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    logger.info("🔵 Initializing OpenAI: %s", model)
    
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL"),
        timeout=kwargs.get("timeout", 60),
        max_retries=kwargs.get("max_retries", 2),
    )


def _get_anthropic(
    model_name: Optional[str],
    temperature: float,
    **kwargs
) -> BaseChatModel:
    """Get Anthropic chat model with lazy import."""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        logger.error("langchain-anthropic not installed. Run: pip install langchain-anthropic")
        raise ImportError(
            "Anthropic support requires 'langchain-anthropic'. "
            "Install with: pip install langchain-anthropic"
        ) from exc
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set in environment")
    
    model = model_name or os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
    
    logger.info("🟠 Initializing Anthropic: %s", model)
    
    return ChatAnthropic(
        model=model,
        temperature=temperature,
        api_key=api_key,
        timeout=kwargs.get("timeout", 60),
        max_retries=kwargs.get("max_retries", 2),
    )


# ─────────────────────────────────────────────────────────────
# Convenience functions for specific layers (Groq-optimized)
# ─────────────────────────────────────────────────────────────

def get_detective_llm(task: str = "code") -> BaseChatModel:
    """
    Get LLM for detective layer tasks.
    
    Groq models are fast and cost-effective for forensic analysis.
    """
    provider = os.getenv("LLM_PROVIDER", "groq")
    
    if task == "code":
        # Code analysis: Llama 3 8B is fast and capable
        return get_llm(
            provider=provider,
            model_name=os.getenv("GROQ_CODE_MODEL", "llama3-8b-8192"),
            temperature=0.2,
        )
    else:
        # Text/PDF analysis: Mixtral for better reasoning
        return get_llm(
            provider=provider,
            model_name=os.getenv("GROQ_DOC_MODEL", "mixtral-8x7b-32768"),
            temperature=0.3,
        )


def get_judge_llm(persona: str = "primary") -> BaseChatModel:
    """
    Get LLM for judicial layer tasks.
    
    Groq Llama 3 70B provides excellent reasoning for judicial personas.
    """
    provider = os.getenv("LLM_PROVIDER", "groq")
    
    if persona == "fallback":
        # Fallback: smaller, faster model
        return get_llm(
            provider=provider,
            model_name=os.getenv("GROQ_FALLBACK_MODEL", "llama3-8b-8192"),
            temperature=0.4,
        )
    else:
        # Primary: Llama 3 70B for best reasoning
        return get_llm(
            provider=provider,
            model_name=os.getenv("GROQ_JUDGE_MODEL", "llama3-70b-8192"),
            temperature=0.4,
        )


# ─────────────────────────────────────────────────────────────
# Provider detection helper
# ─────────────────────────────────────────────────────────────

def detect_available_provider() -> str:
    """
    Detect which LLM provider is configured and available.
    
    Returns: "groq", "ollama", "openai", "anthropic", or "none"
    """
    # Check Groq first (fastest, recommended)
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    
    # Check Ollama (local)
    try:
        import httpx
        response = httpx.get(
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/tags",
            timeout=5
        )
        if response.status_code == 200:
            return "ollama"
    except Exception:
        pass
    
    # Check OpenAI
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    
    # Check Anthropic
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    
    return "none"