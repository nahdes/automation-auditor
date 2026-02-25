"""
src/nodes/detectives.py
───────────────────────
Layer 1: The Detective Layer — Forensic Sub-Agents

Three agents run in PARALLEL via LangGraph fan-out.
They do NOT opinionate. They collect facts only.
Output: structured Evidence objects stored under unique keys in state.evidences.

  RepoInvestigator  → clones + AST-analyses the GitHub repository
  DocAnalyst        → parses and cross-references the PDF report
  VisionInspector   → classifies embedded diagrams via multimodal LLM (optional)
  EvidenceAggregator → fan-in synchronisation barrier
"""

import logging
import os
from typing import Dict, List

from src.state import (
    AgentState, DocEvidence, Evidence, RepoEvidence, VisionEvidence,
)
from src.tools.repo_tools import (
    analyze_graph_structure,
    analyze_state_management,
    analyze_structured_output,
    analyze_tool_sandboxing,
    clone_repo_sandboxed,
    extract_git_history,
    scan_directory_for_python,
)
from src.tools.doc_tools import analyze_pdf_report
from src.tools.vision_tools import analyze_diagrams, vision_evidence_to_evidence

logger = logging.getLogger(__name__)

# Evidence key → rubric dimension mapping (Targeting Protocol from spec)
TARGET_TO_KEYS = {
    "github_repo": [
        "git_forensic_analysis",
        "state_management_rigor",
        "graph_orchestration",
        "safe_tool_engineering",
        "structured_output_enforcement",
        "judicial_nuance",
        "chief_justice_synthesis",
    ],
    "pdf_report": ["theoretical_depth", "report_accuracy"],
    "pdf_images": ["swarm_visual"],
}


# ─────────────────────────────────────────────
#  DETECTIVE 1: RepoInvestigator
# ─────────────────────────────────────────────

def repo_investigator_node(state: AgentState) -> dict:
    """
    RepoInvestigator — The Code Detective.

    Clones the target repo into a sandboxed TemporaryDirectory and runs
    5 forensic protocols via AST analysis (not regex):
      A. Git Forensic Analysis
      B. State Management Rigor
      C. Graph Orchestration Architecture
      D. Safe Tool Engineering
      E. Structured Output Enforcement
    """
    repo_url = state.get("repo_url", "")
    if not repo_url:
        return {
            "errors": ["RepoInvestigator: no repo_url in state"],
            "evidences": {
                "git_forensic_analysis": [_missing_evidence("Clone repository", "no url")],
            },
        }

    logger.info("🔍 RepoInvestigator: cloning %s", repo_url)
    repo_path, tmpdir = clone_repo_sandboxed(repo_url)

    if not repo_path:
        fail = Evidence(
            goal="Clone and analyse repository",
            found=False,
            content="git clone failed",
            location=repo_url,
            rationale="Non-zero exit code or timeout — authentication error or private repo",
            confidence=0.95,
            tags=["clone-failure"],
        )
        return {
            "errors": [f"RepoInvestigator: failed to clone {repo_url}"],
            "evidences": {"git_forensic_analysis": [fail]},
        }

    try:
        logger.info("  Protocol A: Git History")
        git_ev  = extract_git_history(repo_path)

        logger.info("  Protocol B: State Management")
        state_ev = analyze_state_management(repo_path)

        logger.info("  Protocol C: Graph Orchestration")
        graph_ev = analyze_graph_structure(repo_path)

        logger.info("  Protocol D: Tool Sandboxing")
        tools_ev = analyze_tool_sandboxing(repo_path)

        logger.info("  Protocol E: Structured Output")
        output_ev = analyze_structured_output(repo_path)

        py_files_rel = [
            os.path.relpath(f, repo_path)
            for f in scan_directory_for_python(repo_path)[:60]
        ]

        repo_evidence = RepoEvidence(
            git_history=git_ev,
            state_management=state_ev,
            graph_orchestration=graph_ev,
            tool_sandboxing=tools_ev,
            structured_output=output_ev,
            raw_findings={"python_files": py_files_rel},
        )

        logger.info(
            "  ✅ RepoInvestigator done: git=%s state=%s graph=%s tools=%s output=%s",
            git_ev.found, state_ev.found, graph_ev.found, tools_ev.found, output_ev.found,
        )

        return {
            "repo_evidence": repo_evidence,
            "evidences": {
                # Keys match rubric dimension IDs exactly
                "git_forensic_analysis":        [git_ev],
                "state_management_rigor":        [state_ev],
                "graph_orchestration":           [graph_ev],
                "safe_tool_engineering":         [tools_ev],
                "structured_output_enforcement": [output_ev],
            },
        }

    except Exception as exc:
        logger.error("RepoInvestigator crashed: %s", exc, exc_info=True)
        return {"errors": [f"RepoInvestigator crashed: {exc}"]}

    finally:
        if tmpdir:
            try:
                tmpdir.cleanup()
            except Exception as exc:
                logger.warning("Tmpdir cleanup failed: %s", exc)


# ─────────────────────────────────────────────
#  DETECTIVE 2: DocAnalyst
# ─────────────────────────────────────────────

def doc_analyst_node(state: AgentState) -> dict:
    """
    DocAnalyst — The Paperwork Detective.

    Analyses the PDF report for:
      A. Theoretical depth (genuine understanding vs buzzword-dropping)
      B. Hallucination check (claimed file paths vs repo files)

    Note: In the parallel execution the repo_evidence may not yet be available
    (it's written by a sibling branch). We degrade gracefully in that case.
    """
    pdf_path = state.get("pdf_path", "")
    logger.info("📄 DocAnalyst: analysing PDF at %s", pdf_path)

    if not pdf_path or not os.path.exists(pdf_path):
        missing = _missing_evidence("Read PDF report", pdf_path or "not provided")
        return {
            "errors": [f"DocAnalyst: PDF not found at '{pdf_path}'"],
            "evidences": {
                "theoretical_depth": [missing],
                "report_accuracy":   [missing],
            },
        }

    # Best-effort: use repo file list if already in state (may be empty in parallel run)
    repo_ev = state.get("repo_evidence")
    repo_files = []
    repo_root  = ""
    if repo_ev and hasattr(repo_ev, "raw_findings"):
        repo_files = repo_ev.raw_findings.get("python_files", [])

    try:
        doc_evidence = analyze_pdf_report(pdf_path, repo_files, repo_root)

        logger.info(
            "  ✅ DocAnalyst done: depth=%s hallucinations=%s",
            doc_evidence.theoretical_depth.found,
            not doc_evidence.hallucination_check.found,
        )

        return {
            "doc_evidence": doc_evidence,
            "evidences": {
                "theoretical_depth": [doc_evidence.theoretical_depth],
                "report_accuracy":   [doc_evidence.hallucination_check],
            },
        }
    except Exception as exc:
        logger.error("DocAnalyst crashed: %s", exc, exc_info=True)
        return {"errors": [f"DocAnalyst crashed: {exc}"]}


# ─────────────────────────────────────────────
#  DETECTIVE 3: VisionInspector
# ─────────────────────────────────────────────

def vision_inspector_node(state: AgentState) -> dict:
    """
    VisionInspector — The Diagram Detective.

    Extracts images from the PDF and asks a multimodal LLM to classify
    whether the diagram correctly shows the parallel LangGraph topology.
    Execution is optional per the spec — gracefully degrades.
    """
    pdf_path = state.get("pdf_path", "")
    logger.info("🖼️  VisionInspector: extracting diagrams from %s", pdf_path)

    if not pdf_path or not os.path.exists(pdf_path):
        return {
            "errors": [f"VisionInspector: PDF not found at '{pdf_path}'"],
        }

    try:
        vision_ev = analyze_diagrams(pdf_path)
        evidence  = vision_evidence_to_evidence(vision_ev)

        logger.info(
            "  ✅ VisionInspector done: type=%s parallel=%s",
            vision_ev.diagram_type, vision_ev.has_parallel_flow,
        )

        return {
            "vision_evidence": vision_ev,
            "evidences": {"swarm_visual": [evidence]},
        }
    except Exception as exc:
        logger.error("VisionInspector crashed: %s", exc, exc_info=True)
        return {"errors": [f"VisionInspector crashed: {exc}"]}


# ─────────────────────────────────────────────
#  FAN-IN: EvidenceAggregator
# ─────────────────────────────────────────────

def evidence_aggregator_node(state: AgentState) -> dict:
    """
    Synchronisation barrier — waits for ALL parallel detectives to finish.

    Implements the Targeting Protocol from the spec:
      • Validates that every rubric dimension has corresponding evidence
      • Logs a forensic summary of all collected evidence
      • Does NOT mutate state — just validates and logs

    Topology:
      [RepoInvestigator || DocAnalyst || VisionInspector] → EvidenceAggregator → Judges
    """
    evidences = state.get("evidences", {})
    errors    = state.get("errors", [])
    dims      = state.get("rubric_dimensions", [])

    ev_count = sum(len(v) for v in evidences.values())
    logger.info(
        "🔗 EvidenceAggregator: %d items across %d categories",
        ev_count, len(evidences),
    )

    if errors:
        logger.warning("  ⚠  %d detective errors: %s", len(errors), errors[:3])

    # Targeting Protocol: check coverage per dimension
    for dim in dims:
        dim_id = dim.get("id", "")
        if dim_id not in evidences:
            logger.warning("  ⚠  No evidence for dimension '%s'", dim_id)

    # Forensic summary log
    for key in sorted(evidences):
        for ev in evidences[key]:
            icon = "✅" if ev.found else "❌"
            logger.info("  %s [%s] conf=%.2f: %s", icon, key, ev.confidence, ev.rationale[:80])

    return {}  # Fan-in checkpoint — no state mutation needed


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _missing_evidence(goal: str, location: str) -> Evidence:
    return Evidence(
        goal=goal,
        found=False,
        content="Not provided",
        location=location,
        rationale="Input was empty or the file did not exist",
        confidence=0.99,
        tags=["missing"],
    )