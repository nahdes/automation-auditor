"""
src/graph.py
────────────
The Automaton Auditor — Main LangGraph StateGraph
Architecture (two-level parallel fan-out / fan-in):
START
  │
  ▼
ContextBuilder          ← loads week2_rubric.json
│
├─────────────────────────────┐────────────────┐
▼                             ▼                 ▼
RepoInvestigator           DocAnalyst          VisionInspector
│                             │                 │
└──────────────┬──────────────┘─────────────────┘
▼
EvidenceAggregator    ← fan-in barrier
│
┌──────────────┼──────────────┐
▼              ▼              ▼
Prosecutor      Defense       TechLead
│              │              │
└──────┬────────┘──────────────┘
▼
ChiefJustice              ← deterministic synthesis (no LLM)
│
▼
ReportSaver              ← writes Markdown to audit/ dir
│
▼
END
CLI usage:
python -m src.graph <github_url> [pdf_path] [self|peer|received]
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from src.state import AgentState, AuditReport
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
    Entry node: loads week2_rubric.json and injects dimensions + synthesis_rules
    into shared AgentState so every downstream node can access the constitution.
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


def report_saver_node(state: AgentState) -> dict:
    """
    Serialise AuditReport → Markdown and save to the appropriate audit/ subfolder.
    Folder is chosen by audit_type: self | peer | received.
    """
    report = state.get("final_report")
    repo_url = state.get("repo_url", "unknown")
    audit_type = state.get("audit_type", "peer")
    if not report:
        logger.warning("ReportSaver: no AuditReport to save")
        return {}

    md = generate_markdown_report(report)

    base = Path(__file__).parent.parent / "audit"
    dirs = {
        "self": base / "report_onself_generated",
        "peer": base / "report_onpeer_generated",
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
# GRAPH CONSTRUCTION
# ─────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """
    Assemble the hierarchical StateGraph.
    Two parallel fan-out / fan-in cycles:
    Cycle A: ContextBuilder → [3 Detectives] → EvidenceAggregator
    Cycle B: EvidenceAggregator → [3 Judges] → ChiefJustice
    """
    g = StateGraph(AgentState)

    # Register nodes
    g.add_node("ContextBuilder", context_builder_node)
    g.add_node("RepoInvestigator", repo_investigator_node)
    g.add_node("DocAnalyst", doc_analyst_node)
    g.add_node("VisionInspector", vision_inspector_node)
    g.add_node("EvidenceAggregator", evidence_aggregator_node)
    g.add_node("Prosecutor", prosecutor_node)
    g.add_node("Defense", defense_node)
    g.add_node("TechLead", tech_lead_node)
    g.add_node("ChiefJustice", chief_justice_node)
    g.add_node("ReportSaver", report_saver_node)

    # Entry
    g.add_edge(START, "ContextBuilder")

    # Detective fan-out (parallel)
    g.add_edge("ContextBuilder", "RepoInvestigator")
    g.add_edge("ContextBuilder", "DocAnalyst")
    g.add_edge("ContextBuilder", "VisionInspector")

    # Detective fan-in
    g.add_edge("RepoInvestigator", "EvidenceAggregator")
    g.add_edge("DocAnalyst", "EvidenceAggregator")
    g.add_edge("VisionInspector", "EvidenceAggregator")

    # Judicial fan-out (parallel)
    g.add_edge("EvidenceAggregator", "Prosecutor")
    g.add_edge("EvidenceAggregator", "Defense")
    g.add_edge("EvidenceAggregator", "TechLead")

    # Judicial fan-in
    g.add_edge("Prosecutor", "ChiefJustice")
    g.add_edge("Defense", "ChiefJustice")
    g.add_edge("TechLead", "ChiefJustice")

    # Final
    g.add_edge("ChiefJustice", "ReportSaver")
    g.add_edge("ReportSaver", END)

    return g


def compile_graph():
    """Compile and return the executable runnable."""
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
        repo_url:   GitHub repository URL
        pdf_path:   Path to accompanying PDF report (optional)
        audit_type: "self" | "peer" | "received"

    Returns:
        Final AgentState with final_report populated.
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
        "repo_url": repo_url,
        "pdf_path": pdf_path,
        "audit_type": audit_type,
        "rubric_dimensions": [],
        "synthesis_rules": {},
        "evidences": {},
        "opinions": [],
        "errors": [],
        "final_report": None,
        "repo_evidence": None,
        "doc_evidence": None,
        "vision_evidence": None,
    }

    final = compiled.invoke(initial)

    ar = final.get("final_report")
    if ar:
        scores = [cr.final_score for cr in ar.criteria]
        logger.info("\n%s", "=" * 60)
        logger.info("🏁 Audit Complete — Scores: %s | Overall: %.1f/5.0", scores, ar.overall_score)
        logger.info("%s\n", "=" * 60)

    return final


# ──────────────────────────────────────────────
# CLI ENTRY POINT (Fixed)
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m src.graph <github_url> [pdf_path] [self|peer|received]")
        sys.exit(1)

    result = run_audit(
        repo_url=sys.argv[1],
        pdf_path=sys.argv[2] if len(sys.argv) > 2 else "",  # ✅ Fixed: no trailing space
        audit_type=sys.argv[3] if len(sys.argv) > 3 else "peer",  # ✅ Fixed: no trailing space
    )

    ar = result.get("final_report")
    if ar:
        print(generate_markdown_report(ar))
    else:
        print("No report generated. Errors:", result.get("errors", []))