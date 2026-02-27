"""
src/graph.py
────────────
The Automaton Auditor — Main LangGraph StateGraph

Architecture (two-level parallel fan-out / fan-in + conditional error routing):

START
  │
  ▼
ContextBuilder                ← loads week2_rubric.json
  │
  ├──────────────┬──────────────────────┐
  ▼              ▼                      ▼
RepoInvestigator  DocAnalyst     VisionInspector
  │  [cond]       │  [cond]           │  [cond]
  │ ok/err        │ ok/err            │ ok/err
  └──────────────┴──────────────────────┘
                  │ (all converge — fan-in)
                  ▼
          EvidenceAggregator
                  │
          [cond: enough evidence?]
          ┌───────┴────────┐
        "ok"            "fatal"
          │                │
          ├──────┬──────┐   ▼
          ▼      ▼      ▼  ErrorReporter
       Prosecutor Defense TechLead     │
          │      │      │              │
          └──────┴──────┘              │
                  │                   │
                  ▼                   │
           ChiefJustice               │
                  │                   │
                  └─────────┬─────────┘
                            ▼
                       ReportSaver
                            │
                           END

CLI usage:
    python -m src.graph <github_url> [pdf_path] [self|peer|received]
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from src.state import AgentState, AuditReport, CriterionResult
from src.nodes.detectives import (
    doc_analyst_node,
    evidence_aggregator_node,
    repo_investigator_node,
    vision_inspector_node,
)
from src.nodes.judges import defense_node, prosecutor_node, tech_lead_node
from src.nodes.justice import chief_justice_node, generate_markdown_report

logger = logging.getLogger(__name__)
RUBRIC_PATH = Path(__file__).parent.parent / "rubric" / "week2_rubric.json"


# ─────────────────────────────────────────────────────────────
# UTILITY NODES
# ─────────────────────────────────────────────────────────────

def context_builder_node(state: AgentState) -> dict:
    """
    Entry node: loads week2_rubric.json and injects dimensions +
    synthesis_rules into shared AgentState so every downstream node
    can read the constitution without re-opening the file.
    """
    logger.info("🔧 ContextBuilder: loading rubric...")
    if not RUBRIC_PATH.exists():
        logger.error("Rubric not found: %s", RUBRIC_PATH)
        return {"errors": [f"Rubric file not found: {RUBRIC_PATH}"]}

    with open(RUBRIC_PATH) as f:
        rubric = json.load(f)

    dimensions = rubric.get("dimensions", [])
    synthesis_rules = rubric.get("synthesis_rules", {})
    logger.info("  Loaded %d dimensions, %d synthesis rules", len(dimensions), len(synthesis_rules))

    return {
        "rubric_dimensions": dimensions,
        "synthesis_rules": synthesis_rules,
        "evidences": {},
        "opinions": [],
        "errors": [],
        "final_report": None,
    }


def error_reporter_node(state: AgentState) -> dict:
    """
    Fallback node reached when EvidenceAggregator finds zero evidence
    (all three detectives failed).  Writes a diagnostic AuditReport so
    ReportSaver still produces a meaningful file rather than silently
    returning None.
    """
    errors = state.get("errors", [])
    repo_url = state.get("repo_url", "unknown")
    dimensions = state.get("rubric_dimensions", [])

    logger.error("💀 ErrorReporter: no evidence collected — building diagnostic report")
    logger.error("   Errors: %s", errors)

    criteria = [
        CriterionResult(
            dimension_id=d.get("id", "unknown"),
            dimension_name=d.get("name", "Unknown"),
            final_score=1,
            judge_opinions=[],
            dissent_summary="No evidence collected — all detective nodes failed.",
            remediation=(
                "1. Verify the repo URL is public and reachable.\n"
                "2. Check GROQ_API_KEY is valid and quota is not exhausted.\n"
                "3. Re-run: python -m src.graph <url> <pdf> <type>"
            ),
        )
        for d in dimensions
    ]

    report = AuditReport(
        repo_url=repo_url,
        executive_summary=(
            "FATAL: All detective nodes failed — no evidence was collected. "
            "Errors: " + "; ".join(errors[:5])
        ),
        overall_score=0.0,
        criteria=criteria,
        remediation_plan=(
            "Ensure the repository URL is accessible, the PDF path is correct, "
            "and all required API keys are set in .env."
        ),
    )
    return {"final_report": report}


def report_saver_node(state: AgentState) -> dict:
    """
    Serialise AuditReport → Markdown and write to the appropriate
    audit/ subfolder based on audit_type: self | peer | received.
    """
    report = state.get("final_report")
    repo_url = state.get("repo_url", "unknown")
    audit_type = state.get("audit_type", "peer")

    if not report:
        logger.warning("ReportSaver: no AuditReport in state — nothing to save")
        return {}

    md = generate_markdown_report(report)

    base = Path(__file__).parent.parent / "audit"
    dirs = {
        "self":     base / "report_onself_generated",
        "peer":     base / "report_onpeer_generated",
        "received": base / "report_bypeer_received",
    }
    out_dir = dirs.get(audit_type, base / "report_onpeer_generated")
    out_dir.mkdir(parents=True, exist_ok=True)
    (base / "langsmith_logs").mkdir(parents=True, exist_ok=True)

    slug = (repo_url.rstrip("/").split("/")[-1] or "repo")[:40]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"audit_{slug}_{timestamp}.md"

    out_path.write_text(md, encoding="utf-8")
    logger.info("  ✅ Report saved → %s", out_path)
    return {}


# ─────────────────────────────────────────────────────────────
# CONDITIONAL EDGE ROUTING FUNCTIONS
# ─────────────────────────────────────────────────────────────

# Evidence keys each detective is responsible for producing.
# Used to detect whether a crashed detective produced anything at all.
_DETECTIVE_KEYS: Dict[str, set] = {
    "RepoInvestigator": {
        "git_forensic_analysis",
        "state_management_rigor",
        "graph_orchestration",
        "safe_tool_engineering",
        "structured_output_enforcement",
        "judicial_nuance",
        "chief_justice_synthesis",
    },
    "DocAnalyst":      {"theoretical_depth", "report_accuracy"},
    "VisionInspector": {"swarm_visual"},
}


def _route_detective(node_name: str):
    """
    Returns a routing function for the given detective node.

    Logic:
    - If the node logged an error AND produced zero expected evidence keys
      → route "error" (still goes to EvidenceAggregator for fan-in convergence)
    - Otherwise → route "ok"

    Both "ok" and "error" map to EvidenceAggregator because ALL three
    parallel detective branches must converge at the same node before
    the judicial fan-out can be released by LangGraph.  The distinction
    matters for logging and future extension (e.g. retry logic).
    """
    expected = _DETECTIVE_KEYS.get(node_name, set())

    def _route(state: AgentState) -> str:
        errors = state.get("errors", [])
        produced = expected & set(state.get("evidences", {}).keys())
        node_errored = any(node_name in e for e in errors)

        if node_errored and not produced:
            logger.warning(
                "⚠  %s: crashed with no evidence produced — logging error, "
                "continuing to EvidenceAggregator",
                node_name,
            )
            return "error"
        return "ok"

    return _route


def _route_after_aggregation(state: AgentState) -> str:
    """
    Gate between the detective layer and the judicial layer.

    Returns:
        "ok"    → at least one evidence key collected → invoke judges
        "fatal" → zero evidence collected → route to ErrorReporter
    """
    evidences = state.get("evidences", {})
    errors = state.get("errors", [])

    if evidences:
        if errors:
            logger.warning(
                "  Proceeding with %d evidence key(s) despite %d error(s): %s",
                len(evidences), len(errors), errors[:3],
            )
        return "ok"

    logger.error("  Zero evidence after aggregation — routing to ErrorReporter. Errors: %s", errors)
    return "fatal"


# ─────────────────────────────────────────────────────────────
# GRAPH CONSTRUCTION
# ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Assemble the hierarchical StateGraph with conditional error routing.

    Detective layer:
        Each detective uses add_conditional_edges so that a node crash
        is captured in state.errors and the graph continues gracefully
        rather than raising an unhandled exception.  Both the "ok" and
        "error" paths converge on EvidenceAggregator (required for fan-in).

    Post-aggregation gate:
        If zero evidence was collected (all detectives crashed), the
        "fatal" branch routes to ErrorReporter which writes a diagnostic
        report.  Otherwise the "ok" branch releases the judicial fan-out.

    Judicial layer:
        Unconditional parallel fan-out/fan-in — once evidence exists the
        three judges always run and converge on ChiefJustice.
    """
    g = StateGraph(AgentState)

    # ── Register all nodes ──────────────────────────────────
    g.add_node("ContextBuilder",     context_builder_node)
    g.add_node("RepoInvestigator",   repo_investigator_node)
    g.add_node("DocAnalyst",         doc_analyst_node)
    g.add_node("VisionInspector",    vision_inspector_node)
    g.add_node("EvidenceAggregator", evidence_aggregator_node)
    g.add_node("ErrorReporter",      error_reporter_node)
    g.add_node("Prosecutor",         prosecutor_node)
    g.add_node("Defense",            defense_node)
    g.add_node("TechLead",           tech_lead_node)
    g.add_node("ChiefJustice",       chief_justice_node)
    g.add_node("ReportSaver",        report_saver_node)

    # ── Entry ───────────────────────────────────────────────
    g.add_edge(START, "ContextBuilder")

    # ── Detective fan-out (parallel) ────────────────────────
    g.add_edge("ContextBuilder", "RepoInvestigator")
    g.add_edge("ContextBuilder", "DocAnalyst")
    g.add_edge("ContextBuilder", "VisionInspector")

    # ── Detective fan-in WITH conditional error routing ─────
    # Both branches ("ok" and "error") converge on EvidenceAggregator.
    # This satisfies LangGraph's fan-in requirement while capturing
    # which detectives failed without crashing the graph.
    for node in ("RepoInvestigator", "DocAnalyst", "VisionInspector"):
        g.add_conditional_edges(
            node,
            _route_detective(node),
            {
                "ok":    "EvidenceAggregator",
                "error": "EvidenceAggregator",   # still converges for fan-in
            },
        )

    # ── Post-aggregation gate ───────────────────────────────
    # "ok"    → judicial fan-out (Prosecutor branch; others added below)
    # "fatal" → ErrorReporter → ReportSaver
    g.add_conditional_edges(
        "EvidenceAggregator",
        _route_after_aggregation,
        {
            "ok":    "Prosecutor",
            "fatal": "ErrorReporter",
        },
    )
    # Remaining judicial fan-out edges (parallel with Prosecutor)
    g.add_edge("EvidenceAggregator", "Defense")
    g.add_edge("EvidenceAggregator", "TechLead")

    # ── Judicial fan-in ─────────────────────────────────────
    g.add_edge("Prosecutor", "ChiefJustice")
    g.add_edge("Defense",    "ChiefJustice")
    g.add_edge("TechLead",   "ChiefJustice")

    # ── Fatal path ──────────────────────────────────────────
    g.add_edge("ErrorReporter", "ReportSaver")

    # ── Normal completion path ──────────────────────────────
    g.add_edge("ChiefJustice", "ReportSaver")
    g.add_edge("ReportSaver",  END)

    return g


def compile_graph():
    """Compile and return the executable LangGraph runnable."""
    compiled = build_graph().compile()
    logger.info("✅ StateGraph compiled successfully")
    return compiled


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def run_audit(
    repo_url: str,
    pdf_path: str = "",
    audit_type: str = "peer",
) -> Dict[str, Any]:
    """
    Run a complete forensic audit.

    Args:
        repo_url:   GitHub repository URL to audit
        pdf_path:   Path to the accompanying PDF report (optional)
        audit_type: "self" | "peer" | "received"

    Returns:
        Final AgentState dict with final_report populated.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("\n%s", "=" * 60)
    logger.info("🏛  AUTOMATON AUDITOR — Starting Audit")
    logger.info("   Repo:  %s", repo_url)
    logger.info("   PDF:   %s", pdf_path or "Not provided")
    logger.info("   Type:  %s", audit_type)
    logger.info("%s\n", "=" * 60)

    compiled = compile_graph()

    initial: AgentState = {
        "repo_url":          repo_url,
        "pdf_path":          pdf_path,
        "audit_type":        audit_type,
        "rubric_dimensions": [],
        "synthesis_rules":   {},
        "evidences":         {},
        "opinions":          [],
        "errors":            [],
        "final_report":      None,
        "repo_evidence":     None,
        "doc_evidence":      None,
        "vision_evidence":   None,
    }

    final = compiled.invoke(initial)

    ar = final.get("final_report")
    if ar:
        scores = [cr.final_score for cr in ar.criteria]
        logger.info("\n%s", "=" * 60)
        logger.info("🏁 Audit Complete — Scores: %s | Overall: %.1f/5.0", scores, ar.overall_score)
        logger.info("%s\n", "=" * 60)

    return final


# ─────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.graph <github_url> [pdf_path] [self|peer|received]")
        sys.exit(1)

    result = run_audit(
        repo_url=sys.argv[1],
        pdf_path=sys.argv[2] if len(sys.argv) > 2 else "",
        audit_type=sys.argv[3] if len(sys.argv) > 3 else "peer",
    )

    ar = result.get("final_report")
    if ar:
        print(generate_markdown_report(ar))
    else:
        print("No report generated. Errors:", result.get("errors", []))