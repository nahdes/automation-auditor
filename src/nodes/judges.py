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

Ollama Integration:
- Uses langchain_ollama.ChatOllama for local execution
- Falls back to OpenAI/Anthropic if configured
- Model selection via environment variables
"""
import logging
import os
from typing import Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from src.state import AgentState, Evidence, JudicialOpinion
from src.config.langchain_config import get_judge_llm

logger = logging.getLogger(__name__)
MAX_RETRIES = 3


# ─────────────────────────────────────────────────────────────
# LLM FACTORY (Ollama-First with Fallback)
# ─────────────────────────────────────────────────────────────

def _get_llm(temperature: float = 0.4):
    """
    Return LLM with provider priority: Groq → Ollama → OpenAI → Anthropic.
    FIXED: Proper Groq initialization without URL duplication.
    """
    provider = os.getenv("LLM_PROVIDER", "groq")
    
    try:
        if provider == "groq":
            from langchain_groq import ChatGroq
            
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise EnvironmentError("GROQ_API_KEY not set")
            
            model = os.getenv("GROQ_JUDGE_MODEL", "llama3-8b-8192")
            
            logger.info("🚀 Initializing Groq Judge: %s", model)
            
            # ✅ FIXED: No base_url parameter - ChatGroq handles it internally
            return ChatGroq(
                model=model,
                temperature=temperature,
                api_key=api_key,
                timeout=120,  # Increased for reliability
                max_retries=2,
            )
        
        elif provider == "ollama":
            from langchain_ollama import ChatOllama
            model = os.getenv("OLLAMA_JUDGE_MODEL", "llama3.1:8b")
            return ChatOllama(
                model=model,
                temperature=temperature,
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                num_ctx=4096,
                timeout=300,
            )
        
        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=temperature,
                api_key=os.getenv("OPENAI_API_KEY"),
                timeout=60,
            )
        
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
                temperature=temperature,
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout=60,
            )
        
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    except ImportError as exc:
        logger.error("LLM package not installed: %s", exc)
        raise
    except Exception as exc:
        logger.error("LLM initialization failed: %s", exc)
        raise
# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPTS (Deliberately Distinct — No Shared Boilerplate)
# ─────────────────────────────────────────────────────────────

PROSECUTOR_SYSTEM = """
You are THE PROSECUTOR in a Digital Courtroom auditing an AI engineering submission.

CORE PHILOSOPHY: "Trust No One. Assume Vibe Coding."

YOUR MANDATE: Scrutinize every artifact for gaps, security flaws, and lazy shortcuts.

CHARGES YOU MUST ACTIVELY SEEK:
- "Orchestration Fraud": linear pipeline masquerading as parallel execution
- "Security Negligence": raw os.system() without sandboxing
- "Hallucination Liability": Judge nodes returning free text instead of Pydantic objects
- "Auditor Hallucination": PDF claims files/features that the repo does not contain
- "Persona Collusion": three judges sharing >50% identical prompt text
- "Bulk Upload Fraud": single 'init' commit covering entire codebase
- "Technical Debt": plain Python dicts instead of Pydantic BaseModel for state

SENTENCING GUIDELINES:
- Linear graph with no fan-out → LangGraph Architecture score MAX 1
- Judges output free text → Judicial Nuance score MAX 2
- Report cites non-existent files → Report Accuracy score 1
- os.system() detected in cloning logic → Safe Tool Engineering score MAX 2, security_override triggered
- Single init commit → Git Forensic Analysis score MAX 2

Be aggressive. The burden of proof is on the defendant. Evidence not found = not implemented.

You MUST return a valid JudicialOpinion JSON object with these exact fields:
- judge: "Prosecutor"
- criterion_id: the rubric dimension ID being evaluated
- score: integer 1-5
- argument: your full legal reasoning
- cited_evidence: list of evidence keys supporting your argument
- charges: list of violations you are charging
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

You MUST return a valid JudicialOpinion JSON object with these exact fields:
- judge: "Defense"
- criterion_id: the rubric dimension ID being evaluated
- score: integer 1-5
- argument: your full legal reasoning
- cited_evidence: list of evidence keys supporting your argument
- charges: empty list (you defend, you don't charge)
"""

TECH_LEAD_SYSTEM = """
You are THE TECH LEAD in a Digital Courtroom auditing an AI engineering submission.

CORE PHILOSOPHY: "Does it actually work? Is it maintainable? Would I merge this PR?"

YOUR MANDATE: Evaluate architectural soundness, code cleanliness, and practical viability.
You are THE TIE-BREAKER when Prosecutor and Defense disagree.

EVALUATION STANDARDS:
✓ Pydantic BaseModel + TypedDict with reducers → Production-grade
✗ Plain Python dicts for complex nested state → Technical Debt, score 3
✓ tempfile.TemporaryDirectory + subprocess.run → Sandboxed
✗ os.system() without sandbox → Security Negligence, score MAX 2
✓ .with_structured_output() on judges → Structured output
✓ operator.add / operator.ior reducers present → Parallel-safe state
✓ Two fan-out/fan-in cycles in graph → Robust Swarm
✗ Single linear pipeline → Spaghetti Script, score 1

TIE-BREAKING RULE:
If Prosecutor says 1 and Defense says 5 — assess the actual technical debt objectively.
Score 1, 3, or 5 based on whether the CORE requirement was met.

Provide specific file-level remediation instructions.

You MUST return a valid JudicialOpinion JSON object with these exact fields:
- judge: "TechLead"
- criterion_id: the rubric dimension ID being evaluated
- score: integer 1-5
- argument: your full technical assessment
- cited_evidence: list of evidence keys supporting your argument
- charges: empty list (you evaluate, you don't charge)
"""


# ─────────────────────────────────────────────────────────────
# EVIDENCE FORMATTER
# ─────────────────────────────────────────────────────────────

def _format_evidence(state: AgentState, criterion: Dict) -> str:
    """
    Build the evidence block passed to each judge for one criterion.
    Handles both Evidence Pydantic objects AND plain dicts for flexibility.
    """
    evidences = state.get("evidences", {})
    lines = [
        f"=== FORENSIC BRIEF: {criterion['name']} (ID: {criterion['id']}) ===",
        f"Target Artifact: {criterion['target_artifact']}",
        " ",
        "FORENSIC INSTRUCTION:",
        criterion.get("forensic_instruction", "See rubric"),
        " ",
        "SUCCESS PATTERN:",
        criterion.get("success_pattern", " "),
        " ",
        "FAILURE PATTERN:",
        criterion.get("failure_pattern", " "),
        " ",
        "=== COLLECTED EVIDENCE ===",
    ]
    
    for key, ev_list in sorted(evidences.items()):
        for ev in ev_list:
            # Handle both Evidence object AND plain dict
            if isinstance(ev, dict):
                # Dict access
                found = ev.get("found", False)
                goal = ev.get("goal", "N/A")
                confidence = ev.get("confidence", 0.0)
                location = ev.get("location", "N/A")
                rationale = ev.get("rationale", "N/A")
                content = ev.get("content", "")
                tags = ev.get("tags", [])
            else:
                # Pydantic Evidence object access
                found = ev.found
                goal = ev.goal
                confidence = ev.confidence
                location = ev.location
                rationale = ev.rationale
                content = ev.content if hasattr(ev, 'content') else ""
                tags = ev.tags if hasattr(ev, 'tags') else []
            
            icon = "✅" if found else "❌"
            lines.append(f"\n[{key}] {icon}")
            lines.append(f"  Goal:       {goal}")
            lines.append(f"  Found:      {found}")
            lines.append(f"  Confidence: {confidence:.2f}")
            lines.append(f"  Location:   {location}")
            lines.append(f"  Rationale:  {rationale}")
            if content:
                preview = content[:600] + ("…" if len(content) > 600 else "")
                lines.append(f"  Content:    {preview}")
            if tags:
                lines.append(f"  Tags:       {', '.join(tags)}")

    lines.append("\n=== YOUR JUDICIAL LOGIC FOR THIS CRITERION ===")
    jl = criterion.get("judicial_logic", {})
    for role, instruction in jl.items():
        lines.append(f"\n{role.upper()}: {instruction}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# JUDGE INVOCATION WITH STRUCTURED OUTPUT + RETRY
# ─────────────────────────────────────────────────────────────

def _invoke_judge(
    persona: str,
    system_prompt: str,
    evidence_block: str,
    criterion_id: str,
) -> Optional[JudicialOpinion]:
    """
    Call a judge LLM with structured output enforcement.
    Retries up to MAX_RETRIES times if output is not valid Pydantic.
    
    Args:
        persona: Judge persona name ("Prosecutor", "Defense", or "TechLead")
        system_prompt: System prompt for the judge persona
        evidence_block: Formatted evidence context
        criterion_id: Rubric dimension ID being evaluated
        
    Returns:
        JudicialOpinion object or None if all retries fail
    """
    try:
        # Get LLM with Ollama integration
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
                        "  ⚖  %s → %s: score=%d", 
                        persona, criterion_id, result.score
                    )
                    return result
                    
                logger.warning(
                    "  %s attempt %d: unexpected type %s", 
                    persona, attempt, type(result)
                )
                
            except Exception as exc:
                logger.warning("  %s attempt %d failed: %s", persona, attempt, exc)
                if attempt == MAX_RETRIES:
                    raise

    except EnvironmentError as exc:
        logger.error("LLM not configured: %s", exc)
        # Deterministic fallback when no LLM is available
        return JudicialOpinion(
            judge=persona,  # type: ignore[arg-type]
            criterion_id=criterion_id,
            score=3,
            argument=f"[LLM UNAVAILABLE] Default score assigned. {exc}",
            cited_evidence=[],
            charges=["LLM_UNAVAILABLE"],
        )
    except Exception as exc:
        logger.error("%s failed after %d retries: %s", persona, MAX_RETRIES, exc)
        return None


# ─────────────────────────────────────────────────────────────
# GENERIC JUDGE NODE FACTORY
# ─────────────────────────────────────────────────────────────

def _judge_node(state: AgentState, persona: str, system_prompt: str) -> dict:
    """
    Run one judicial persona across ALL 10 rubric criteria.
    
    Args:
        state: Current AgentState
        persona: Judge persona name
        system_prompt: System prompt for the persona
        
    Returns:
        Dict with opinions list for state reducer
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

    logger.info(
        "  ✅ %s issued %d opinions across %d criteria", 
        persona, len(opinions), len(dimensions)
    )
    return {"opinions": opinions}


# ─────────────────────────────────────────────────────────────
# JUDGE NODES (Registered in graph.py)
# ─────────────────────────────────────────────────────────────

def prosecutor_node(state: AgentState) -> dict:
    """
    The Prosecutor — finds violations, charges fraud, argues for low scores.
    
    Args:
        state: Current AgentState
        
    Returns:
        Dict with prosecutor opinions
    """
    logger.info("⚔  Prosecutor: building case...")
    return _judge_node(state, "Prosecutor", PROSECUTOR_SYSTEM)


def defense_node(state: AgentState) -> dict:
    """
    The Defense Attorney — champions effort, intent, and spirit of the law.
    
    Args:
        state: Current AgentState
        
    Returns:
        Dict with defense opinions
    """
    logger.info("🛡  Defense: building defence...")
    return _judge_node(state, "Defense", DEFENSE_SYSTEM)


def tech_lead_node(state: AgentState) -> dict:
    """
    The Tech Lead — pragmatic tiebreaker focused on production viability.
    
    Args:
        state: Current AgentState
        
    Returns:
        Dict with tech lead opinions
    """
    logger.info("🔧  TechLead: evaluating architecture...")
    return _judge_node(state, "TechLead", TECH_LEAD_SYSTEM)