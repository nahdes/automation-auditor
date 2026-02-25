"""
src/state.py
────────────
Core Pydantic and TypedDict state definitions for the Automaton Auditor.
Models match the spec EXACTLY:
Evidence         – Detective output (forensic fact object)
JudicialOpinion  – Judge output (one opinion per criterion)
CriterionResult  – Chief Justice output per dimension
AuditReport      – Final structured report → serialised to Markdown
AgentState       – LangGraph TypedDict with annotated reducers
Design principles:
• operator.ior  merges evidence dicts without key collision (parallel-safe)
• operator.add  appends opinion lists from concurrent judge branches
• Pydantic BaseModel enforces runtime validation on all domain objects
• TypedDict is used for AgentState because LangGraph requires it
"""
import operator
from typing import Annotated, Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ─────────────────────────────────────────────────────────────
# DETECTIVE LAYER — Evidence objects (no opinions, pure facts)
# ─────────────────────────────────────────────────────────────

class Evidence(BaseModel):
    """A single forensic evidence object collected by a Detective agent."""
    goal: str = Field(description="What this evidence was collected to verify")
    found: bool = Field(description="Whether the artifact or pattern exists")
    content: Optional[str] = Field(default=None, description="Raw evidence snippet or excerpt")
    location: str = Field(description="File path, line number, or commit hash")
    rationale: str = Field(
        description="Your rationale for your confidence on the evidence "
                    "you find for this particular goal"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="0.0–1.0 confidence score")
    tags: List[str] = Field(default_factory=list, description="Labels e.g. ['security','pydantic']")


class RepoEvidence(BaseModel):
    """Aggregated findings from the RepoInvestigator across all 5 forensic protocols."""
    git_history: Evidence
    state_management: Evidence
    graph_orchestration: Evidence
    tool_sandboxing: Evidence
    structured_output: Evidence
    raw_findings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form data: python_files list, node/edge counts, etc."
    )


class DocEvidence(BaseModel):
    """Aggregated findings from the DocAnalyst (PDF report analysis)."""
    theoretical_depth: Evidence
    hallucination_check: Evidence
    cross_references: List[Dict[str, str]] = Field(
        default_factory=list,
        description="[{claim, file_path, verified: true/false}, ...]"
    )
    deep_concepts_found: List[str] = Field(default_factory=list)


class VisionEvidence(BaseModel):
    """Findings from the VisionInspector (diagram analysis via multimodal LLM)."""
    diagram_type: str = Field(default="unknown")
    has_parallel_flow: bool = Field(default=False)
    flow_description: str = Field(default="No diagram analysed")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ─────────────────────────────────────────────────────────────
# JUDICIAL LAYER — Opinion objects (one per judge per criterion)
# ─────────────────────────────────────────────────────────────

class JudicialOpinion(BaseModel):
    """One judge's verdict on a single rubric criterion."""
    judge: Literal["Prosecutor", "Defense", "TechLead"]
    criterion_id: str = Field(description="Must match a dimension 'id' in week2_rubric.json")
    score: int = Field(ge=1, le=5, description="Score 1–5 for this criterion")
    argument: str = Field(description="The judge's full legal argument with evidence citations")
    cited_evidence: List[str] = Field(
        description="List of evidence keys that support this argument"
    )
    charges: List[str] = Field(
        default_factory=list,
        description="Violations charged e.g. ['Orchestration Fraud', 'Security Negligence']"
    )


# ─────────────────────────────────────────────────────────────
# SUPREME COURT — Verdict and Report objects
# ─────────────────────────────────────────────────────────────

class CriterionResult(BaseModel):
    """Chief Justice final verdict on a single rubric criterion."""
    dimension_id: str
    dimension_name: str
    final_score: int = Field(ge=1, le=5)
    judge_opinions: List[JudicialOpinion]
    dissent_summary: Optional[str] = Field(
        default=None,
        description="Required when score variance > 2 (dissent_requirement rule)"
    )
    remediation: str = Field(
        description="Specific file-level instructions for improvement"
    )
    overrides_applied: List[str] = Field(
        default_factory=list,
        description="Named constitutional rules applied e.g. 'security_override'"
    )


class AuditReport(BaseModel):
    """
    Complete structured audit report.
    Serialised to Markdown as the final_report in AgentState.
    Structure: Executive Summary → Criterion Breakdown → Remediation Plan
    """
    repo_url: str
    executive_summary: str
    overall_score: float
    criteria: List[CriterionResult]
    remediation_plan: str


# ─────────────────────────────────────────────────────────────
# AGENT STATE — TypedDict + Annotated reducers (LangGraph)
# ─────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """
    Shared state across the entire LangGraph swarm.
    Reducer rules:
      evidences: operator.ior  → dict-union so RepoInvestigator and DocAnalyst
                                  both survive parallel writes (last key wins is
                                   safe because each detective uses unique keys)
      opinions:  operator.add  → list-append so all three judges accumulate
                                  without overwriting each other
      errors:    operator.add  → accumulates errors from any node
    """
    # ── Inputs ────────────────────────────────────────────────
    repo_url: str
    pdf_path: str
    audit_type: str          # "self" | "peer" | "received"
    rubric_dimensions: List[Dict]   # loaded from week2_rubric.json
    synthesis_rules: Dict[str, Any]

    # ── Detective outputs (parallel-safe via reducers) ─────────
    evidences: Annotated[Dict[str, List[Evidence]], operator.ior]

    # Typed detective findings (optional — may be None before node runs)
    repo_evidence: Optional[RepoEvidence]
    doc_evidence: Optional[DocEvidence]
    vision_evidence: Optional[VisionEvidence]

    # ── Judicial outputs (parallel-safe via reducer) ───────────
    opinions: Annotated[List[JudicialOpinion], operator.add]

    # ── Supreme Court output ───────────────────────────────────
    final_report: Optional[AuditReport]

    # ── Error tracking (accumulated across all nodes) ──────────
    errors: Annotated[List[str], operator.add]