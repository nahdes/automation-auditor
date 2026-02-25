"""
src/tools/doc_tools.py
──────────────────────
Forensic tools for the DocAnalyst (Paperwork Detective).
Implements:
• PDF ingestion with chunking (RAG-lite) — tries docling → pypdf → pdfminer
• Theoretical-depth keyword + context verification
• Cross-reference hallucination check (claimed file paths vs repo files)
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.state import DocEvidence, Evidence

logger = logging.getLogger(__name__)

# Concepts whose presence AND explanation depth are required
DEEP_CONCEPTS = [
    "Dialectical Synthesis",
    "Fan-In",
    "Fan-Out",
    "Metacognition",
    "State Synchronization",
    "Multi-Agent",
    "LangGraph",
    "Pydantic",
]

DEPTH_INDICATORS = [
    "because", "therefore", "this means", "in practice",
    "the architecture", "we implemented", "this ensures",
    "by using", "which allows", "this prevents",
    "is executed by", "results in", "enables",
]


# ─────────────────────────────────────────────────────────────
# PDF INGESTION — RAG-LITE
# ─────────────────────────────────────────────────────────────

def ingest_pdf(path: str) -> List[Dict[str, str]]:
    """
    Parse a PDF into ~500-word text chunks.
    Tries docling → pypdf → pdfminer in order.
    Returns: [{"page": str, "text": str}, ...]
    """
    if not Path(path).exists():
        logger.warning("PDF not found: %s", path)
        return []

    # 1. docling (richest, markdown-aware)
    try:
        from docling.document_converter import DocumentConverter
        result = DocumentConverter().convert(path)
        md = result.document.export_to_markdown()
        words = md.split()
        chunks = []
        for i in range(0, len(words), 500):
            chunks.append({"page": f"chunk_{i//500}", "text": " ".join(words[i:i+500])})
        if chunks:
            logger.info("docling: %d chunks from %s", len(chunks), path)
            return chunks
    except ImportError:
        logger.debug("docling not installed")
    except Exception as exc:
        logger.warning("docling failed: %s", exc)

    # 2. pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        chunks = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                chunks.append({"page": str(i + 1), "text": text})
        if chunks:
            logger.info("pypdf: %d pages from %s", len(chunks), path)
            return chunks
    except ImportError:
        logger.debug("pypdf not installed")
    except Exception as exc:
        logger.warning("pypdf failed: %s", exc)

    # 3. pdfminer
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer
        chunks = []
        for i, layout in enumerate(extract_pages(path)):
            text = " ".join(
                elem.get_text() for elem in layout if isinstance(elem, LTTextContainer)
            )
            if text.strip():
                chunks.append({"page": str(i + 1), "text": text})
        if chunks:
            logger.info("pdfminer: %d pages from %s", len(chunks), path)
            return chunks
    except ImportError:
        logger.debug("pdfminer not installed")
    except Exception as exc:
        logger.warning("pdfminer failed: %s", exc)

    logger.error("No PDF library could parse %s — install pypdf", path)
    return []


def query_chunks(chunks: List[Dict[str, str]], query: str, top_k: int = 3) -> List[str]:
    """Keyword-based chunk retrieval (RAG-lite). Returns top_k most relevant chunks."""
    q = query.lower()
    scored = sorted(
        ((sum(1 for w in q.split() if w in c["text"].lower()), c["text"]) for c in chunks),
        reverse=True,
    )
    return [text for score, text in scored[:top_k] if score > 0]


# ─────────────────────────────────────────────────────────────
# FORENSIC PROTOCOL A — THEORETICAL DEPTH
# ─────────────────────────────────────────────────────────────

def analyze_theoretical_depth(chunks: List[Dict[str, str]]) -> Evidence:
    """
    Check for deep conceptual understanding vs. buzzword-dropping.
    A concept must appear in a substantive explanation, not just the intro.
    """
    full_text = " ".join(c["text"] for c in chunks)
    lower = full_text.lower()
    found_concepts: List[str] = []
    context_snippets: List[str] = []

    for concept in DEEP_CONCEPTS:
        idx = lower.find(concept.lower())
        if idx >= 0:
            found_concepts.append(concept)
            start = max(0, idx - 150)
            end = min(len(full_text), idx + 250)
            context_snippets.append(f"[{concept}]: ...{full_text[start:end].strip()}...")

    depth_score = sum(1 for phrase in DEPTH_INDICATORS if phrase in lower)
    has_deep = len(found_concepts) >= 3 and depth_score >= 4
    confidence = min(
        0.95,
        (len(found_concepts) / len(DEEP_CONCEPTS)) * 0.65 + (depth_score / 10) * 0.35,
    )

    return Evidence(
        goal="Verify deep theoretical understanding of multi-agent orchestration concepts",
        found=has_deep,
        content="\n\n".join(context_snippets[:5]) or "No relevant concepts found",
        location="pdf_report",
        rationale=(
            f"Found {len(found_concepts)}/{len(DEEP_CONCEPTS)} concepts: {found_concepts}.  "
            f"Depth indicators: {depth_score}/10.  "
            f"Assessment: {'Deep understanding' if has_deep else 'Keyword-dropping suspected'}."
        ),
        confidence=confidence,
        tags=["theoretical-depth", "deep" if has_deep else "shallow"],
    )


# ─────────────────────────────────────────────────────────────
# FORENSIC PROTOCOL B — HALLUCINATION CHECK
# ─────────────────────────────────────────────────────────────

def extract_file_claims(chunks: List[Dict[str, str]]) -> List[str]:
    """Extract all file-path claims from PDF text using a regex pattern."""
    text = " ".join(c["text"] for c in chunks)
    pattern = r'(?:src/|./)[\w/._-]+\.(?:py|json|md|txt|yaml|yml|toml)'
    return list(set(re.findall(pattern, text)))


def cross_reference_claims(
    chunks: List[Dict[str, str]],
    repo_files: List[str],
    repo_root: str,
) -> Evidence:
    """
    Cross-reference file-path claims in the PDF against actual repo files.
    Builds Verified Paths and Hallucinated Paths lists.
    """
    claimed = extract_file_claims(chunks)
    if not claimed:
        return Evidence(
            goal="Cross-reference PDF file path claims against repo contents",
            found=True,
            content="No specific file paths claimed in the PDF",
            location="pdf_report",
            rationale="No file paths were mentioned — nothing to cross-reference",
            confidence=0.50,
            tags=["cross-reference", "no-claims"],
        )

    import os
    repo_relative: set = set()
    for f in repo_files:
        try:
            rel = os.path.relpath(f, repo_root)
            repo_relative.add(rel.replace("\\", "/"))
        except Exception:
            pass

    verified: List[str] = []
    hallucinated: List[str] = []

    for claim in claimed:
        normalised = claim.lstrip("./").replace("\\", "/")
        if normalised in repo_relative or any(normalised in r for r in repo_relative):
            verified.append(claim)
        else:
            hallucinated.append(claim)

    all_clean = len(hallucinated) == 0
    confidence = 0.92 if all_clean else max(0.20, len(verified) / max(len(claimed), 1))

    lines = []
    if verified:
        lines.append(f"✅ Verified ({len(verified)}): {verified}")
    if hallucinated:
        lines.append(f"❌ Hallucinated ({len(hallucinated)}): {hallucinated}")

    return Evidence(
        goal="Cross-reference PDF file path claims against actual repository files",
        found=all_clean,
        content="\n".join(lines),
        location="pdf_report + github_repo",
        rationale=(
            f"{len(verified)} verified, {len(hallucinated)} hallucinated  "
            f"out of {len(claimed)} claims.  "
            + ("All claims verified." if all_clean
               else f"WARNING: {len(hallucinated)} non-existent paths claimed.")
        ),
        confidence=confidence,
        tags=["cross-reference"] + (["clean"] if all_clean else ["hallucinations-found"]),
    )


# ─────────────────────────────────────────────────────────────
# MAIN ANALYSIS ENTRY POINT
# ─────────────────────────────────────────────────────────────

def analyze_pdf_report(
    pdf_path: str,
    repo_files: List[str],
    repo_root: str,
) -> DocEvidence:
    """
    Full DocAnalyst forensic pipeline for one PDF report.
    Gracefully handles missing PDF or parse failures.
    """
    import os
    if not os.path.exists(pdf_path):
        blank = Evidence(
            goal="Read PDF report",
            found=False,
            content="File not found",
            location=pdf_path,
            rationale="PDF was not provided or path is invalid",
            confidence=0.97,
            tags=["missing-document"],
        )
        return DocEvidence(
            theoretical_depth=blank,
            hallucination_check=blank,
        )

    chunks = ingest_pdf(pdf_path)
    if not chunks:
        blank = Evidence(
            goal="Parse PDF content",
            found=False,
            content="No text extracted — image-only PDF or parse failure",
            location=pdf_path,
            rationale="PDF parsed but returned zero text chunks",
            confidence=0.80,
            tags=["parse-failure"],
        )
        return DocEvidence(
            theoretical_depth=blank,
            hallucination_check=blank,
        )

    theoretical = analyze_theoretical_depth(chunks)
    hallu_check = cross_reference_claims(chunks, repo_files, repo_root)
    lower = " ".join(c["text"] for c in chunks).lower()
    found_conc = [c for c in DEEP_CONCEPTS if c.lower() in lower]

    return DocEvidence(
        theoretical_depth=theoretical,
        hallucination_check=hallu_check,
        cross_references=[],
        deep_concepts_found=found_conc,
    )