"""
src/nodes/judges.py
───────────────────
Layer 2: The Judicial Layer — The Dialectical Bench

Three judges run in PARALLEL for ALL 10 rubric criteria,
each with a completely distinct philosophical lens:

  Prosecutor  →  "Trust No One. Assume Vibe Coding."
  Defense     →  "Reward Effort and Intent."
  TechLead    →  "Does it actually work? Is it maintainable?"

All judges use .with_structured_output(JudicialOpinion) to enforce
Pydantic validation. Free-text responses trigger a retry (up to 3x).
"""

import logging
import os
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.state import AgentState, Evidence, JudicialOpinion

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


# ─────────────────────────────────────────────
#  LLM FACTORY
# ─────────────────────────────────────────────

def _get_llm(temperature: float = 0.3):
    """Return LLM. Tries OpenAI GPT-4o first, then Anthropic Claude."""
    if os.environ.get("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o", temperature=temperature)
    if os.environ.get("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-opus-4-6", temperature=temperature)
    raise EnvironmentError(
        "No LLM API key. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env"
    )


# ─────────────────────────────────────────────
#  SYSTEM PROMPTS  (deliberately distinct — no shared boilerplate)
# ─────────────────────────────────────────────

PROSECUTOR_SYSTEM = """
You are THE PROSECUTOR in a Digital Courtroom auditing an AI engineering submission.

CORE PHILOSOPHY: "Trust No One. Assume Vibe Coding."
YOUR MANDATE: Scrutinize every artifact for gaps, security flaws, and lazy shortcuts.

CHARGES YOU MUST ACTIVELY SEEK:
- "Orchestration Fraud"      : linear pipeline masquerading as parallel execution
- "Security Negligence"      : raw os.system() without sandboxing
- "Hallucination Liability"  : Judge nodes returning free text instead of Pydantic objects
- "Auditor Hallucination"    : PDF claims files/features that the repo does not contain
- "Persona Collusion"        : three judges sharing >50% identical prompt text
- "Bulk Upload Fraud"        : single 'init' commit covering entire codebase
- "Technical Debt"           : plain Python dicts instead of Pydantic BaseModel for state

SENTENCING GUIDELINES:
- Linear graph with no fan-out             → LangGraph Architecture score MAX 1
- Judges output free text                  → Judicial Nuance score MAX 2
- Report cites non-existent files          → Report Accuracy score 1
- os.system() detected in cloning logic    → Safe Tool Engineering score MAX 2, security_override triggered
- Single init commit                       → Git Forensic Analysis score MAX 2

Be aggressive. The burden of proof is on the defendant. Evidence not found = not implemented.
You MUST return a valid JudicialOpinion JSON object.
"""

DEFENSE_SYSTEM = """
You are THE DEFENSE ATTORNEY in a Digital Courtroom auditing an AI engineering submission.

CORE PHILOSOPHY: "Reward Effort and Intent. Look for the Spirit of the Law."
YOUR MANDATE: Find genuine engineering effort, creative workarounds, and deep understanding,
even when the implementation is imperfect or incomplete.

MITIGATION STRATEGIES:
- Graph fails to compile but AST parsing is sophisticated → argue Score 3 for Forensic Accuracy
- Commit history shows struggle and iteration (many commits) → boost score based on process
- Pydantic used correctly even if graph wiring is simple → highlight architectural soundness
- Report explains concepts deeply even if not all features implemented → credit understanding
- Minor syntax errors on otherwise correct architecture → "Spirit of the Law" argument
- ChiefJustice uses LLM synthesis but personas are genuinely distinct → partial credit Score 3-4

SCORING MANDATE:
- Find the highest DEFENSIBLE score for each criterion
- Benefit of the doubt on ambiguous evidence
- Effort and deep thought deserve more credit than copy-pasted working code

You MUST return a valid JudicialOpinion JSON object.
"""

TECH_LEAD_SYSTEM = """
You are THE TECH LEAD in a Digital Courtroom auditing an AI engineering submission.

CORE PHILOSOPHY: "Does it actually work? Is it maintainable? Would I merge this PR?"
YOUR MANDATE: Evaluate architectural soundness, code cleanliness, and practical viability.
You are THE TIE-BREAKER when Prosecutor and Defense disagree.

EVALUATION STANDARDS:
- Pydantic BaseModel + TypedDict with reducers → Production-grade ✓
- Plain Python dicts for complex nested state  → Technical Debt, score 3
- tempfile.TemporaryDirectory + subprocess.run → Sandboxed ✓
- os.system() without sandbox                 → Security Negligence, score MAX 2
- .with_structured_output() on judges         → Structured output ✓
- operator.add / operator.ior reducers present → Parallel-safe state ✓
- Two fan-out/fan-in cycles in graph          → Robust Swarm ✓
- Single linear pipeline                      → Spaghetti Script, score 1

TIE-BREAKING RULE:
If Prosecutor says 1 and Defense says 5 — assess the actual technical debt objectively.
Score 1, 3, or 5 based on whether the CORE requirement was met.
Provide specific file-level remediation instructions.

You MUST return a valid JudicialOpinion JSON object.
"""


# ─────────────────────────────────────────────
#  EVIDENCE FORMATTER
# ─────────────────────────────────────────────

def _format_evidence(state: AgentState, criterion: Dict) -> str:
    """Build the evidence block passed to each judge for one criterion."""
    evidences = state.get("evidences", {})
    lines = [
        f"=== FORENSIC BRIEF: {criterion['name']} (ID: {criterion['id']}) ===",
        f"Target Artifact: {criterion['target_artifact']}",
        "",
        "FORENSIC INSTRUCTION:",
        criterion.get("forensic_instruction", "See rubric"),
        "",
        "SUCCESS PATTERN:",
        criterion.get("success_pattern", ""),
        "",
        "FAILURE PATTERN:",
        criterion.get("failure_pattern", ""),
        "",
        "=== COLLECTED EVIDENCE ===",
    ]

    for key, ev_list in sorted(evidences.items()):
        for ev in ev_list:
            icon = "✅" if ev.found else "❌"
            lines.append(f"\n[{key}] {icon}")
            lines.append(f"  Goal:       {ev.goal}")
            lines.append(f"  Found:      {ev.found}")
            lines.append(f"  Confidence: {ev.confidence:.2f}")
            lines.append(f"  Location:   {ev.location}")
            lines.append(f"  Rationale:  {ev.rationale}")
            if ev.content:
                preview = ev.content[:600] + ("…" if len(ev.content) > 600 else "")
                lines.append(f"  Content:    {preview}")
            if ev.tags:
                lines.append(f"  Tags:       {', '.join(ev.tags)}")

    lines.append("\n=== YOUR JUDICIAL LOGIC FOR THIS CRITERION ===")
    jl = criterion.get("judicial_logic", {})
    for role, instruction in jl.items():
        lines.append(f"\n{role.upper()}: {instruction}")

    return "\n".join(lines)


# ─────────────────────────────────────────────
#  JUDGE INVOCATION WITH STRUCTURED OUTPUT + RETRY
# ─────────────────────────────────────────────

def _invoke_judge(
    persona: str,
    system_prompt: str,
    evidence_block: str,
    criterion_id: str,
) -> Optional[JudicialOpinion]:
    """
    Call a judge LLM with structured output enforcement.
    Retries up to MAX_RETRIES times if output is not valid Pydantic.
    Returns JudicialOpinion or a fallback if all retries fail.
    """
    try:
        llm = _get_llm(temperature=0.4)
        structured_llm = llm.with_structured_output(JudicialOpinion)

        human = (
            f"Render your verdict on criterion: {criterion_id}\n\n"
            f"{evidence_block}\n\n"
            f"Your 'judge' field MUST be exactly: \"{persona}\"\n"
            f"Your 'criterion_id' MUST be exactly: \"{criterion_id}\"\n"
            f"Return a JudicialOpinion JSON object now."
        )

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = structured_llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human),
                ])
                if isinstance(result, JudicialOpinion):
                    logger.info(
                        "  ⚖  %s → %s: score=%d", persona, criterion_id, result.score
                    )
                    return result
                logger.warning(
                    "  %s attempt %d: unexpected type %s", persona, attempt, type(result)
                )
            except Exception as exc:
                logger.warning("  %s attempt %d failed: %s", persona, attempt, exc)
                if attempt == MAX_RETRIES:
                    raise

    except EnvironmentError as exc:
        logger.error("LLM not configured: %s", exc)
        # Deterministic fallback when no LLM is available
        return JudicialOpinion(
            judge=persona,          # type: ignore[arg-type]
            criterion_id=criterion_id,
            score=3,
            argument=f"[LLM UNAVAILABLE] Default score assigned. {exc}",
            cited_evidence=[],
            charges=["LLM_UNAVAILABLE"],
        )
    except Exception as exc:
        logger.error("%s failed after %d retries: %s", persona, MAX_RETRIES, exc)
        return None


# ─────────────────────────────────────────────
#  GENERIC JUDGE NODE FACTORY
# ─────────────────────────────────────────────

def _judge_node(state: AgentState, persona: str, system_prompt: str) -> dict:
    """
    Run one judicial persona across ALL 10 rubric criteria.
    Returns opinions list (operator.add reducer appends them to shared state).
    """
    dimensions = state.get("rubric_dimensions", [])
    if not dimensions:
        return {"errors": [f"{persona}: No rubric dimensions in state"]}

    opinions: List[JudicialOpinion] = []
    for criterion in dimensions:
        evidence_block = _format_evidence(state, criterion)
        opinion = _invoke_judge(
            persona=persona,
            system_prompt=system_prompt,
            evidence_block=evidence_block,
            criterion_id=criterion["id"],
        )
        if opinion:
            opinions.append(opinion)
        else:
            logger.error("  %s: no opinion for %s", persona, criterion["id"])

    logger.info("  ✅ %s issued %d opinions across %d criteria", persona, len(opinions), len(dimensions))
    return {"opinions": opinions}


# ─────────────────────────────────────────────
#  JUDGE NODES (registered in graph.py)
# ─────────────────────────────────────────────

def prosecutor_node(state: AgentState) -> dict:
    """The Prosecutor — finds violations, charges fraud, argues for low scores."""
    logger.info("⚔  Prosecutor: building case...")
    return _judge_node(state, "Prosecutor", PROSECUTOR_SYSTEM)


def defense_node(state: AgentState) -> dict:
    """The Defense Attorney — champions effort, intent, and spirit of the law."""
    logger.info("🛡  Defense: building defence...")
    return _judge_node(state, "Defense", DEFENSE_SYSTEM)


def tech_lead_node(state: AgentState) -> dict:
    """The Tech Lead — pragmatic tiebreaker focused on production viability."""
    logger.info("🔧  TechLead: evaluating architecture...")
    return _judge_node(state, "TechLead", TECH_LEAD_SYSTEM)