"""
src/config/ollama_config.py
───────────────────────────
Ollama model configuration for Automaton Auditor.
Centralized model selection with fallback logic.
"""
import os
from typing import Dict, Optional
from pydantic import BaseModel, Field


class OllamaModel(BaseModel):
    """Model configuration for Ollama."""
    name: str
    base_url: str = "http://localhost:11434"
    temperature: float = 0.3
    num_ctx: int = 8192  # Context window
    num_predict: int = 2048  # Max tokens
    timeout: int = 120  # Seconds


class OllamaConfig(BaseModel):
    """Complete Ollama configuration for all agent layers."""
    
    # Detective Layer
    code_analyst: OllamaModel = Field(
        default_factory=lambda: OllamaModel(
            name="qwen2.5-coder:7b",
            temperature=0.2,  # Lower for factual analysis
            num_ctx=8192,
        )
    )
    
    doc_analyst: OllamaModel = Field(
        default_factory=lambda: OllamaModel(
            name="llama3.2:3b",
            temperature=0.3,
            num_ctx=8192,
        )
    )
    
    # Judicial Layer
    judge_primary: OllamaModel = Field(
        default_factory=lambda: OllamaModel(
            name="mistral-nemo:12b",
            temperature=0.4,  # Higher for creative arguments
            num_ctx=8192,
        )
    )
    
    judge_fallback: OllamaModel = Field(
        default_factory=lambda: OllamaModel(
            name="llama3.1:8b",
            temperature=0.4,
            num_ctx=8192,
        )
    )
    
    # Global settings
    base_url: str = "http://localhost:11434"
    request_timeout: int = 300
    max_retries: int = 3
    
    @classmethod
    def from_env(cls) -> 'OllamaConfig':
        """Load configuration from environment variables."""
        return cls(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            request_timeout=int(os.getenv("OLLAMA_TIMEOUT", "300")),
        )
    
    def get_model_for_layer(self, layer: str) -> OllamaModel:
        """Get model configuration for a specific layer."""
        mapping = {
            "code_analyst": self.code_analyst,
            "doc_analyst": self.doc_analyst,
            "judge": self.judge_primary,
            "judge_fallback": self.judge_fallback,
        }
        return mapping.get(layer, self.judge_primary)


# Global configuration instance
ollama_config = OllamaConfig.from_env()