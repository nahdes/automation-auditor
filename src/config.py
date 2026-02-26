"""
src/config.py
─────────────
Configuration validation and environment variable management.
"""
import logging
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
# Load .env at module import time (works for tests + main app)
load_dotenv(override=True)   # override=True so it always wins over system env
logger = logging.getLogger(__name__)
class Settings(BaseModel):
    """Application settings with validation."""
    
    # LLM Configuration
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="OpenAI model name")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    
    # LangSmith
    langchain_tracing_v2: bool = Field(default=True)
    langchain_api_key: Optional[str] = Field(default=None)
    langchain_project: str = Field(default="automaton-auditor")
    
    # Git Configuration
    git_clone_depth: int = Field(default=50, ge=1, le=100)
    git_timeout: int = Field(default=120, ge=30, le=600)
    
    # Agent Configuration
    max_retries: int = Field(default=3, ge=1, le=10)
    judge_temperature: float = Field(default=0.3, ge=0.0, le=1.0)
    
    # Paths
    rubric_path: Path = Field(default=Path("rubric/week2_rubric.json"))
    audit_dir: Path = Field(default=Path("audit"))
    
    @field_validator('openai_api_key')
    @classmethod
    def validate_openai_key(cls, v):
        if not v.startswith('sk-'):
            raise ValueError('Invalid OpenAI API key format')
        return v
    
    @classmethod
    def from_env(cls) -> 'Settings':
        """Load settings from environment variables."""
        return cls(
            openai_api_key=os.getenv('OPENAI_API_KEY', ''),
            openai_model=os.getenv('OPENAI_MODEL', 'gpt-4o'),
            anthropic_api_key=os.getenv('ANTHROPIC_API_KEY'),
            langchain_tracing_v2=os.getenv('LANGCHAIN_TRACING_V2', 'true').lower() == 'true',
            langchain_api_key=os.getenv('LANGCHAIN_API_KEY'),
            langchain_project=os.getenv('LANGCHAIN_PROJECT', 'automaton-auditor'),
            git_clone_depth=int(os.getenv('GIT_CLONE_DEPTH', '50')),
            git_timeout=int(os.getenv('GIT_TIMEOUT', '120')),
            max_retries=int(os.getenv('MAX_RETRIES', '3')),
            judge_temperature=float(os.getenv('JUDGE_TEMPERATURE', '0.3')),
        )
    
    def validate_api_keys(self) -> None:
        """Validate that at least one LLM API key is configured."""
        if not self.openai_api_key and not self.anthropic_api_key:
            raise ValueError(
                "No LLM API key configured. "
                "Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env"
            )

# Global settings instance
settings = Settings.from_env()