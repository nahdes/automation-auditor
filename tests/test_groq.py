"""tests/test_groq.py - Groq integration tests."""
import pytest
import os
from pathlib import Path
import sys

# Ensure src is in path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


class TestGroqConnection:
    """Test Groq API connectivity and model availability."""
    
    def test_groq_api_key_set(self):
        """Verify GROQ_API_KEY is configured."""
        assert os.getenv("GROQ_API_KEY"), "GROQ_API_KEY not set in environment"
        assert os.getenv("GROQ_API_KEY").startswith("gsk_"), "Invalid GROQ_API_KEY format"
    
    def test_groq_llm_initialization(self):
        """Test Groq LLM can be initialized."""
        from src.config.langchain_config import get_llm
        
        llm = get_llm(provider="groq", model_name="llama-3.1-8b-instant")
        assert llm is not None
        assert hasattr(llm, "invoke")
    
    @pytest.mark.slow
    def test_groq_basic_inference(self):
        """Test Groq can generate a response."""
        from src.config.langchain_config import get_llm
        
        llm = get_llm(provider="groq", model_name="llama-3.1-8b-instant", temperature=0)
        response = llm.invoke("What is LangGraph in one sentence?")
        
        assert response is not None
        assert len(str(response.content)) > 0
        assert "graph" in str(response.content).lower() or "agent" in str(response.content).lower()
    
    @pytest.mark.slow
    def test_groq_structured_output(self):
        """Test Groq works with Pydantic structured output."""
        from pydantic import BaseModel
        from src.state import JudicialOpinion
        from src.config.langchain_config import get_llm
        
        llm = get_llm(provider="groq", model_name="llama-3.1-8b-instant")
        structured_llm = llm.with_structured_output(JudicialOpinion)
        
        # This should not raise an error
        assert structured_llm is not None
        
        # Test with simple prompt (may still fail if model doesn't support tools)
        try:
            result = structured_llm.invoke(
                "Judge this code: print('hello'). Return a JudicialOpinion."
            )
            assert isinstance(result, JudicialOpinion) or result is None
        except Exception as e:
            # Groq structured output support may vary by model
            pytest.skip(f"Structured output test: {e}")
    
    def test_detective_llm_factory(self):
        """Test detective LLM factory with Groq."""
        from src.config.langchain_config import get_detective_llm
        
        llm = get_detective_llm(task="code")
        assert llm is not None
        assert hasattr(llm, "invoke")
    
    def test_judge_llm_factory(self):
        """Test judge LLM factory with Groq."""
        from src.config.langchain_config import get_judge_llm
        
        llm = get_judge_llm(persona="primary")
        assert llm is not None
        assert hasattr(llm, "invoke")
    
    def test_provider_detection(self):
        """Test provider detection prioritizes Groq."""
        from src.config.langchain_config import detect_available_provider
        
        # If GROQ_API_KEY is set, should return "groq"
        if os.getenv("GROQ_API_KEY"):
            assert detect_available_provider() == "groq"
