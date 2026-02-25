# test_judge_simple.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))

from src.state import AgentState
from src.nodes.judges import prosecutor_node

# Minimal state with ONE criterion
state: AgentState = {
    "repo_url": "https://github.com/test/repo",
    "pdf_path": "",
    "audit_type": "self",
    "rubric_dimensions": [{
        "id": "state_management_rigor",
        "name": "State Management Rigor", 
        "target_artifact": "github_repo",
        "forensic_instruction": "Check for Pydantic state",
        "success_pattern": "Pydantic found",
        "failure_pattern": "No Pydantic",
        "judicial_logic": {"prosecutor": "Score 1 if missing"}
    }],
    "synthesis_rules": {},
    "evidences": {
        "state_management_rigor": [{
            "goal": "Check Pydantic",
            "found": True,
            "content": "class AgentState(TypedDict)",
            "location": "src/state.py",
            "rationale": "TypedDict found",
            "confidence": 0.9,
            "tags": ["pydantic"]
        }]
    },
    "opinions": [],
    "errors": [],
    "final_report": None,
    "repo_evidence": None,
    "doc_evidence": None,
    "vision_evidence": None,
}

print("🧪 Running prosecutor_node with minimal state...")
result = prosecutor_node(state)
print(f"✅ Result: {len(result.get('opinions', []))} opinions")
if result.get('opinions'):
    op = result['opinions'][0]
    print(f"   Judge: {op.judge}, Score: {op.score}")
    print(f"   Argument: {op.argument[:100]}...")
else:
    print(f"   Errors: {result.get('errors')}")