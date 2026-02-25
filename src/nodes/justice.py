"""
src/nodes/justice.py
─────────────────────
Layer 3: The Supreme Court — Final Verdict
The ChiefJusticeNode synthesises the dialectical conflict from Layer 2
into a final, actionable ruling using DETERMINISTIC PYTHON LOGIC — not an LLM prompt.
Constitutional rules applied (from synthesis_rules in week2_rubric.json):
security_override      — confirmed security flaw caps score at 3
fact_supremacy         — forensic evidence overrules judicial interpretation
functionality_weight   — TechLead confirmation carries highest weight for Architecture
dissent_requirement    — variance > 2 MUST include dissent summary
variance_re_evaluation — variance > 2 triggers cited-evidence re-examination first
Report structure: Executive Summary → Criterion Breakdown → Remediation Plan
"""
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from src.state import (
    AgentState, AuditReport, CriterionResult, Evidence, JudicialOpinion,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# SECURITY VIOLATION DETECTION
# ─────────────────────────────────────────────────────────────

_SECURITY_TAGS = {
    "Security Negligence", "security violation", "shell injection",
    "os.system", "unsanitized", "raw os.system",
}


def _has_security_violation(opinions: List[JudicialOpinion]) -> bool:
    """
    Rule of Security: Prosecutor must have charged a confirmed security vulnerability.
    Detects via charge strings OR (score ≤ 2 AND 'security' in argument).
    """
    for op in opinions:
        if op.judge != "Prosecutor":
            continue
        for charge in op.charges:
            if any(tag.lower() in charge.lower() for tag in _SECURITY_TAGS):
                return True
        if op.score <= 2 and "security" in op.argument.lower():
            return True
    return False


def _has_defense_hallucination(opinions: List[JudicialOpinion], evidences: dict) -> bool:
    """
    Rule of Evidence (fact_supremacy): if Defense claims deep metacognition
    but the PDF was never found, the Defense is overruled.
    """
    doc_evs = evidences.get("theoretical_depth", [])
    for ev in doc_evs:
        if not ev.found and "not found" in ev.rationale.lower():
            return True
    return False


# ─────────────────────────────────────────────────────────────
# DETERMINISTIC SCORE RESOLUTION
# ─────────────────────────────────────────────────────────────

def _resolve_scores(
    p: int, d: int, t: int, criterion_id: str,
) -> Tuple[int, str, bool]:
    """
    Hardcoded Python conflict resolution — NOT an LLM prompt.
    Ladder (in priority order):
      variance ≤ 1  → consensus average (rounded)
      variance == 2 → TechLead tiebreaker (Rule of Functionality)
      variance  >  2 → re-evaluation flag set; TechLead×2 weighted average

    Returns (final_score, method_description, needs_re_evaluation)
    """
    variance = max(p, d, t) - min(p, d, t)
    needs_re_eval = variance > 2

    if variance <= 1:
        final = round((p + d + t) / 3)
        method = f"Consensus (variance={variance}): averaged all three judges"
    elif variance == 2:
        final = t  # Rule of Functionality: TechLead is tiebreaker
        method = f"TechLead tiebreaker (variance={variance}): Tech Lead score accepted"
    else:
        # High conflict — TechLead double-weighted after re-evaluation
        final = round((p + t * 2 + d) / 4)
        method = (
            f"Weighted resolution (HIGH CONFLICT variance={variance}):  "
            f"TechLead×2 + Prosecutor×1 + Defense×1 =  "
            f"({p} + {t*2} + {d}) / 4 = {final}"
        )

    return final, method, needs_re_eval


# ─────────────────────────────────────────────────────────────
# CONSTITUTIONAL OVERRIDES
# ─────────────────────────────────────────────────────────────

def _apply_overrides(
    score: int,
    criterion_id: str,
    opinions: List[JudicialOpinion],
    evidences: dict,
) -> Tuple[int, List[str]]:
    """
    Apply the three named constitutional override rules.
    Returns (possibly_capped_score, list_of_applied_overrides).
    """
    overrides: List[str] = []

    # Rule 1 — security_override
    if _has_security_violation(opinions) and score > 3:
        overrides.append(
            "SECURITY_OVERRIDE: Confirmed security vulnerability capped score at 3 "
            "(synthesis_rules.security_override)."
        )
        score = min(score, 3)

    # Rule 2 — fact_supremacy
    if _has_defense_hallucination(opinions, evidences):
        overrides.append(
            "FACT_SUPREMACY: Defense claimed theoretical depth but no PDF report "
            "was found by the Detective — Defense overruled for hallucination "
            "(synthesis_rules.fact_supremacy)."
        )
        for op in opinions:
            if op.judge == "Defense" and op.score > 3:
                score = min(score, 3)
                break

    return score, overrides


# ─────────────────────────────────────────────────────────────
# VARIANCE RE-EVALUATION
# ─────────────────────────────────────────────────────────────

def _re_evaluate(
    criterion_id: str,
    opinions: List[JudicialOpinion],
    evidences: dict,
) -> str:
    """
    variance_re_evaluation: when variance > 2, re-examine each judge's
    cited evidence for verifiability before accepting the final score.
    Returns a dissent summary string.
    """
    all_keys = set(evidences.keys())
    lines = [
        f"⚠ HIGH-VARIANCE RE-EVALUATION — criterion '{criterion_id}'",
        "",
    ]
    for judge_label in ["Prosecutor", "Defense", "TechLead"]:
        op = next((o for o in opinions if o.judge == judge_label), None)
        if not op:
            continue
        verified = [k for k in op.cited_evidence if k in all_keys]
        unverified = [k for k in op.cited_evidence if k not in all_keys]

        lines.append(f"**{judge_label}** (score {op.score}):")
        lines.append(f"  Argument: {op.argument[:180]}…")
        if verified:
            lines.append(f"  Evidence verified: {', '.join(verified)}")
        if unverified:
            lines.append(f"  Evidence NOT in state: {', '.join(unverified)} ← weakens argument")
        lines.append("")

    # Determine whose argument has stronger forensic backing
    p_op = next((o for o in opinions if o.judge == "Prosecutor"), None)
    d_op = next((o for o in opinions if o.judge == "Defense"), None)
    p_ver = len([k for k in (p_op.cited_evidence if p_op else []) if k in all_keys])
    d_ver = len([k for k in (d_op.cited_evidence if d_op else []) if k in all_keys])

    if p_ver > d_ver:
        lines.append(
            "Re-evaluation finding: Prosecutor has stronger forensic backing.  "
            "TechLead score accepted as final (Rule of Functionality)."
        )
    elif d_ver > p_ver:
        lines.append(
            "Re-evaluation finding: Defense has stronger forensic backing.  "
            "Score adjusted upward from weighted average."
        )
    else:
        lines.append(
            "Re-evaluation finding: Equal forensic backing.  "
            "TechLead tiebreaker accepted per Rule of Functionality."
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# MARKDOWN REPORT GENERATOR
# ─────────────────────────────────────────────────────────────

def generate_markdown_report(report: AuditReport) -> str:
    """
    Serialise AuditReport → structured Markdown.
    Structure: Executive Summary → Criterion Breakdown → Remediation Plan
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append("# 🏛 Automaton Auditor — Forensic Audit Report")
    lines.append(f"> Generated: {now}")
    lines.append(f"> Repository: `{report.repo_url}`")
    lines.append(" ")
    lines.append("---")
    lines.append(" ")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append(" ")
    lines.append(report.executive_summary)
    lines.append(" ")

    n = len(report.criteria)
    max_sc = n * 5
    pct = (report.overall_score / 5.0) * 100 if report.overall_score else 0
    verdict = (
        "PASS — Master Thinker" if pct >= 80 else
        "PASS — Competent Orchestrator" if pct >= 60 else
        "BORDERLINE — Vibe Coder with Potential" if pct >= 40 else
        "FAIL — Vibe Coder"
    )

    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Overall Score | **{report.overall_score:.1f} / 5.0** |")
    lines.append(f"| Percentage | {pct:.1f}% |")
    lines.append(f"| Verdict | **{verdict}** |")
    lines.append(f"| Criteria Evaluated | {n} / 10 |")
    lines.append(" ")
    lines.append("### Score Summary")
    lines.append(" ")
    lines.append("| # | Criterion | Score | Override |")
    lines.append("|---|-----------|-------|---------|")
    for i, cr in enumerate(report.criteria, 1):
        flag = "⚠ OVERRIDE" if cr.overrides_applied else "—"
        lines.append(f"| {i} | {cr.dimension_name} | **{cr.final_score}/5** | {flag} |")
    lines.append(" ")
    lines.append("---")
    lines.append(" ")

    # Criterion Breakdown
    lines.append("## Criterion Breakdown")
    lines.append(" ")
    for cr in report.criteria:
        lines.append(f"### {cr.dimension_name}")
        lines.append(f"**Final Score: {cr.final_score}/5**")
        lines.append(" ")

        for ov in cr.overrides_applied:
            lines.append(f"> 🔴 {ov}")
        if cr.overrides_applied:
            lines.append(" ")

        lines.append("#### Judge Opinions")
        lines.append(" ")
        icons = {"Prosecutor": "⚔", "Defense": "🛡", "TechLead": "🔧"}
        for op in cr.judge_opinions:
            icon = icons.get(op.judge, "⚖")
            lines.append(f"**{icon} {op.judge}** — Score: {op.score}/5")
            lines.append(f"> {op.argument}")
            if op.cited_evidence:
                lines.append(f"> *Cited:* {', '.join(op.cited_evidence)}")
            if op.charges:
                lines.append(f"> *Charges:* {', '.join(op.charges)}")
            lines.append(" ")

        if cr.dissent_summary:
            lines.append("#### ⚖ Dissent Summary")
            lines.append(" ")
            lines.append(cr.dissent_summary)
            lines.append(" ")

        lines.append("#### Remediation")
        lines.append(" ")
        lines.append(cr.remediation)
        lines.append(" ")
        lines.append("---")
        lines.append(" ")

    # Remediation Plan
    lines.append("## Remediation Plan")
    lines.append(" ")
    lines.append(report.remediation_plan)
    lines.append(" ")
    lines.append("---")
    lines.append(" ")
    lines.append(
        "_This report was generated by the Automaton Auditor —  "
        "a hierarchical LangGraph swarm implementing the Digital Courtroom architecture._"
    )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# CHIEF JUSTICE NODE
# ─────────────────────────────────────────────────────────────

def chief_justice_node(state: AgentState) -> dict:
    """
    ChiefJusticeNode — The Supreme Court.
    Applies FIVE deterministic constitutional rules in order:
      1. security_override      → cap score at 3 for security violations
      2. fact_supremacy         → detective evidence over rules judicial opinion
      3. functionality_weight   → TechLead is tiebreaker for architecture criterion
      4. dissent_requirement    → variance > 2 MUST produce a dissent summary
      5. variance_re_evaluation → variance > 2 triggers cited-evidence re-examination

    Does NOT make an LLM call. Pure Python logic.
    """
    logger.info("🏛 ChiefJustice: beginning synthesis...")

    opinions = state.get("opinions", [])
    evidences = state.get("evidences", {})
    dimensions = state.get("rubric_dimensions", [])
    repo_url = state.get("repo_url", "unknown")

    if not opinions:
        logger.warning("ChiefJustice: no opinions received")
        fallback = AuditReport(
            repo_url=repo_url,
            executive_summary="⚠ No judicial opinions received — judicial layer may not have run.",
            overall_score=0.0,
            criteria=[],
            remediation_plan="Run the full audit with all three judges enabled.",
        )
        return {"final_report": fallback, "errors": ["ChiefJustice: no opinions"]}

    # Group opinions by criterion
    by_criterion: Dict[str, List[JudicialOpinion]] = defaultdict(list)
    for op in opinions:
        by_criterion[op.criterion_id].append(op)

    dim_lookup = {d["id"]: d for d in dimensions}
    results: List[CriterionResult] = []
    all_remediations: List[str] = []
    total_score = 0.0

    for criterion_id, crit_opinions in by_criterion.items():
        dim = dim_lookup.get(criterion_id, {})
        dim_name = dim.get("name", criterion_id)

        p_op = next((o for o in crit_opinions if o.judge == "Prosecutor"), None)
        d_op = next((o for o in crit_opinions if o.judge == "Defense"), None)
        t_op = next((o for o in crit_opinions if o.judge == "TechLead"), None)

        p = p_op.score if p_op else 3
        d = d_op.score if d_op else 3
        t = t_op.score if t_op else 3

        logger.info("  [%s] P=%d D=%d T=%d", criterion_id, p, d, t)

        # Step 1 — resolve scores (deterministic rules)
        final_score, resolution, needs_re_eval = _resolve_scores(p, d, t, criterion_id)

        # Step 2 — variance_re_evaluation (rule 5)
        dissent: Optional[str] = None
        if needs_re_eval:
            logger.info("  [%s] HIGH VARIANCE — triggering re-evaluation", criterion_id)
            dissent = _re_evaluate(criterion_id, crit_opinions, evidences)

        # Step 3 — override rules (rules 1 + 2)
        final_score, overrides = _apply_overrides(
            final_score, criterion_id, crit_opinions, evidences
        )

        # Step 4 — dissent_requirement (rule 4)
        variance = max(p, d, t) - min(p, d, t)
        if variance > 2 and not dissent:
            dissent = (
                f"Dissent: Prosecutor={p}, Defense={d}, TechLead={t}.  "
                f"Resolution: {resolution}."
            )
        if overrides:
            dissent = (dissent or "") + "\n" + "\n".join(overrides)

        # Step 5 — build remediation
        parts = []
        if t_op:
            parts.append(f"**Tech Lead:** {t_op.argument}")
        if p_op and p_op.charges:
            for c in p_op.charges:
                parts.append(f"- Fix required: {c}")
        remediation = "\n".join(parts) or f"No specific remediation required for {dim_name}."
        all_remediations.append(f"### {dim_name}\n{remediation}")

        result = CriterionResult(
            dimension_id=criterion_id,
            dimension_name=dim_name,
            final_score=final_score,
            judge_opinions=crit_opinions,
            dissent_summary=dissent,
            remediation=remediation,
            overrides_applied=overrides,
        )
        results.append(result)
        total_score += final_score
        logger.info(
            "  [%s] Final=%d%s",
            criterion_id, final_score,
            " [OVERRIDDEN]" if overrides else "",
        )

    n = len(results)
    overall = total_score / n if n > 0 else 0.0
    pct = (overall / 5.0) * 100

    grade, summary_line = (
        ("Master Thinker", "Submission demonstrates deep architectural understanding.")
        if pct >= 80 else
        ("Competent Orchestrator", "Core requirements met with room for improvement.")
        if pct >= 60 else
        ("Vibe Coder with Potential", "Significant gaps; fundamental patterns present but incomplete.")
        if pct >= 40 else
        ("Vibe Coder", "Critical architectural requirements are missing.")
    )

    security_count = sum(
        1 for cr in results if any("SECURITY" in o for o in cr.overrides_applied)
    )

    exec_summary = (
        f"**Verdict: {grade}**\n\n"
        f"{summary_line}\n\n"
        f"- **Overall Score:** {overall:.1f} / 5.0 ({pct:.1f}%)\n"
        f"- **Criteria Evaluated:** {n} of {len(dimensions)}\n"
        f"- **Security Violations:** {security_count} override(s) applied\n"
        f"- **Synthesis Method:** Deterministic conflict resolution (5 constitutional rules)\n\n"
        f"The three-judge dialectical bench (Prosecutor, Defense, TechLead) evaluated  "
        f"{n} rubric criteria. The Chief Justice applied constitutional override rules  "
        f"to produce this final verdict."
    )

    audit_report = AuditReport(
        repo_url=repo_url,
        executive_summary=exec_summary,
        overall_score=overall,
        criteria=results,
        remediation_plan=(
            "The following file-level fixes are ordered by impact:\n\n"
            + "\n\n".join(all_remediations)
        ),
    )

    logger.info(
        "✅ ChiefJustice done. Score=%.1f/5.0 (%.1f%%) — %s",
        overall, pct, grade,
    )
    return {"final_report": audit_report}