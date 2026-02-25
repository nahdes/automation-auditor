"""tests/test_ollama.py"""
import pytest
from src.config.langchain_config import get_llm, get_detective_llm, get_judge_llm


class TestOllamaConnection:
    """Test Ollama connectivity and model availability."""
    
    def test_ollama_service_running(self):
        """Verify Ollama service is accessible."""
        import httpx
        response = httpx.get("http://localhost:11434/api/tags")
        assert response.status_code == 200
        assert "models" in response.json()
    
    def test_code_analyst_model(self):
        """Test qwen2.5-coder:7b for code analysis."""
        llm = get_detective_llm(task="code")
        response = llm.invoke("What is a Pydantic BaseModel?")
        assert response is not None
        assert len(response.content) > 0
    
    def test_judge_model(self):
        """Test mistral-nemo:12b for judicial reasoning."""
        llm = get_judge_llm(persona="primary")
        response = llm.invoke(
            "Evaluate this code quality on a scale of 1-5: print('hello')"
        )
        assert response is not None
        assert len(response.content) > 0
    
    def test_structured_output(self):
        """Test structured output with Pydantic schema."""
        from pydantic import BaseModel
        from src.state import JudicialOpinion
        
        llm = get_judge_llm()
        structured_llm = llm.with_structured_output(JudicialOpinion)
        
        # This should not raise an error
        assert structured_llm is not None