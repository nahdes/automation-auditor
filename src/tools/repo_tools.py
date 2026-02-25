"""
src/tools/repo_tools.py
───────────────────────
Forensic tools for the RepoInvestigator (Code Detective).

Key design principles:
  • AST-based analysis, NOT regex — robust, not brittle
  • Sandboxed git via tempfile.TemporaryDirectory + subprocess.run
  • Graceful error handling for all system-level calls
  • Returns structured Evidence objects, never raw strings
"""

import ast
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.state import Evidence

logger = logging.getLogger(__name__)

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".tox"}


# ─────────────────────────────────────────────
#  SANDBOXED GIT OPERATIONS
# ─────────────────────────────────────────────

def clone_repo_sandboxed(
    repo_url: str,
    depth: int = 50,
    timeout: int = 120,
) -> Tuple[Optional[str], Optional[tempfile.TemporaryDirectory]]:
    """
    Clone a repository into an isolated TemporaryDirectory.

    Safety contract:
      • Never uses os.system — all subprocess calls capture stdout/stderr
      • Clone target is always tmpdir.name, never CWD
      • Caller MUST call tmpdir.cleanup() to free disk space
      • On any failure, cleanup is performed here and (None, None) is returned

    Returns:
        (repo_path, tmpdir) on success  |  (None, None) on failure
    """
    tmpdir = tempfile.TemporaryDirectory(prefix="auditor_clone_")
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", str(depth), repo_url, tmpdir.name],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.error("git clone failed [rc=%d]: %s", result.returncode, result.stderr[:300])
            tmpdir.cleanup()
            return None, None
        logger.info("Cloned %s → %s", repo_url, tmpdir.name)
        return tmpdir.name, tmpdir

    except subprocess.TimeoutExpired:
        logger.error("git clone timed out after %ds", timeout)
        tmpdir.cleanup()
        return None, None

    except Exception as exc:
        logger.error("clone_repo_sandboxed unexpected error: %s", exc)
        tmpdir.cleanup()
        return None, None


def extract_git_history(repo_path: str) -> Evidence:
    """
    Forensic Protocol — Git Narrative.
    Runs git log --oneline --reverse and classifies as atomic vs monolithic.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--reverse", "--format=%H|%ai|%s"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return _error_evidence("Verify atomic git commit history", repo_path,
                                   "git log returned non-zero", result.stderr)

        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        commits = []
        for line in lines:
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0], "timestamp": parts[1], "message": parts[2]})

        n = len(commits)
        messages = [c["message"].lower() for c in commits]
        bulk_keywords = ["init", "initial commit", "first commit", "add all",
                         "upload", "done", "finished", "complete"]
        is_monolithic = n <= 1 or any(kw in m for m in messages for kw in bulk_keywords)

        content = "\n".join(
            f"  {c['timestamp'][:10]} | {c['message']}" for c in commits[:25]
        )
        confidence = 0.85 if (not is_monolithic and n > 3) else 0.25

        return Evidence(
            goal="Verify atomic git commit history (>3 commits, step-by-step progression)",
            found=not is_monolithic and n > 3,
            content=content,
            location=f"{repo_path}/.git",
            rationale=(
                f"{n} commits found. "
                + ("Progressive development detected." if not is_monolithic
                   else "Monolithic / bulk upload pattern detected.")
            ),
            confidence=confidence,
            tags=["git", "atomic" if not is_monolithic else "monolithic"],
        )

    except subprocess.TimeoutExpired:
        return _error_evidence("Verify atomic git commit history", repo_path, "timeout", "30s")
    except Exception as exc:
        return _error_evidence("Verify atomic git commit history", repo_path, str(exc), "")


# ─────────────────────────────────────────────
#  AST VISITOR
# ─────────────────────────────────────────────

class ASTVisitor(ast.NodeVisitor):
    """
    Walk a Python AST and extract structural metadata:
      classes       – name + base class names + line number
      function_calls – fully qualified call strings (e.g. 'builder.add_edge')
      imports        – module paths (Import + ImportFrom)
      assignments    – unparsed assignment statements
    """

    def __init__(self):
        self.classes:        List[Dict[str, Any]] = []
        self.function_calls: List[str] = []
        self.imports:        List[str] = []
        self.assignments:    List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self.classes.append({
            "name":   node.name,
            "bases":  [ast.unparse(b) for b in node.bases],
            "lineno": node.lineno,
        })
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        try:
            self.function_calls.append(ast.unparse(node.func))
        except Exception:
            pass
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}")

    def visit_Assign(self, node: ast.Assign):
        try:
            self.assignments.append(ast.unparse(node))
        except Exception:
            pass
        self.generic_visit(node)


def parse_python_file(filepath: str) -> Optional[ASTVisitor]:
    """Parse one .py file and return a populated ASTVisitor, or None on error."""
    try:
        src = Path(filepath).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=filepath)
        visitor = ASTVisitor()
        visitor.visit(tree)
        return visitor
    except SyntaxError as exc:
        logger.debug("SyntaxError in %s: %s", filepath, exc)
        return None
    except Exception as exc:
        logger.debug("Error parsing %s: %s", filepath, exc)
        return None


def scan_directory_for_python(root: str) -> List[str]:
    """Recursively find all .py files, excluding virtualenvs and cache dirs."""
    py_files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                py_files.append(os.path.join(dirpath, fname))
    return py_files


# ─────────────────────────────────────────────
#  FORENSIC PROTOCOL A — STATE MANAGEMENT
# ─────────────────────────────────────────────

def analyze_state_management(repo_path: str) -> Evidence:
    """
    Check for typed state: Pydantic BaseModel + TypedDict with operator reducers.
    Looks in src/state.py, src/graph.py, state.py (in that priority order).
    """
    candidates = [
        os.path.join(repo_path, "src", "state.py"),
        os.path.join(repo_path, "src", "graph.py"),
        os.path.join(repo_path, "state.py"),
    ]

    found_pydantic   = False
    found_typed_dict = False
    found_reducers   = False
    snippet          = ""
    location         = "Not found"

    for fpath in candidates:
        if not os.path.exists(fpath):
            continue
        v = parse_python_file(fpath)
        if not v:
            continue
        location = fpath

        pydantic_classes  = [c for c in v.classes if "BaseModel" in c["bases"]]
        typeddict_classes = [c for c in v.classes if "TypedDict" in c["bases"]]

        if pydantic_classes:
            found_pydantic = True
            snippet += f"Pydantic classes: {[c['name'] for c in pydantic_classes]}\n"
        if typeddict_classes:
            found_typed_dict = True
            snippet += f"TypedDict classes: {[c['name'] for c in typeddict_classes]}\n"

        # Check for operator reducers in imports + assignments
        has_operator_import = any("operator" in imp for imp in v.imports)
        has_reducer_assign  = any(
            "operator.add" in a or "operator.ior" in a for a in v.assignments
        )
        if has_operator_import or has_reducer_assign:
            found_reducers = True

    found      = found_pydantic and found_typed_dict
    confidence = 0.92 if (found and found_reducers) else (0.60 if found else 0.15)

    return Evidence(
        goal="Verify typed state with Pydantic BaseModel + TypedDict and operator reducers",
        found=found,
        content=snippet.strip() or "No relevant state files found",
        location=location,
        rationale=(
            f"Pydantic={found_pydantic}, TypedDict={found_typed_dict}, "
            f"Reducers(operator.add/ior)={found_reducers}"
        ),
        confidence=confidence,
        tags=["pydantic", "typed-dict", "state"] + (["reducers"] if found_reducers else []),
    )


# ─────────────────────────────────────────────
#  FORENSIC PROTOCOL B — GRAPH ORCHESTRATION
# ─────────────────────────────────────────────

def analyze_graph_structure(repo_path: str) -> Evidence:
    """
    Detect LangGraph StateGraph with parallel fan-out/fan-in.
    Uses add_edge call counts and node name analysis.
    """
    graph_files: List[Tuple[str, ASTVisitor]] = []

    for fpath in scan_directory_for_python(repo_path):
        v = parse_python_file(fpath)
        if not v:
            continue
        if any("langgraph" in imp or "StateGraph" in imp for imp in v.imports):
            graph_files.append((fpath, v))
        elif any("StateGraph" in call for call in v.function_calls):
            graph_files.append((fpath, v))

    if not graph_files:
        return Evidence(
            goal="Verify LangGraph StateGraph with parallel fan-out/fan-in",
            found=False,
            content="No LangGraph imports found",
            location=repo_path,
            rationale="LangGraph is not imported anywhere in the codebase",
            confidence=0.90,
            tags=["langgraph", "missing"],
        )

    has_parallel = False
    has_fan_in   = False
    snippets: List[str] = []

    for fpath, v in graph_files:
        add_edges = [c for c in v.function_calls if "add_edge" in c]
        add_nodes = [c for c in v.function_calls if "add_node" in c]
        all_text  = " ".join(v.function_calls + v.assignments + v.imports).lower()

        # Multiple edges from same source = fan-out heuristic
        if len(add_edges) >= 5:
            has_parallel = True

        # Explicit parallel/fan-out signals
        if any(kw in all_text for kw in ["send", "parallel", "fan_out", "fan_in", "fanout"]):
            has_parallel = True

        # Fan-in aggregation signals
        if any(kw in all_text for kw in ["aggregat", "synchroniz", "fan_in", "collect", "barrier"]):
            has_fan_in = True

        # Inspect node names for detective/judge naming
        node_args = [c for c in v.function_calls if "add_node" in c]
        all_args = " ".join(node_args).lower()
        if any(kw in all_args for kw in ["prosecutor", "defense", "judge", "techlead"]):
            has_parallel = True  # Judicial layer present

        rel = os.path.relpath(fpath, repo_path)
        snippets.append(f"{rel}: {len(add_nodes)} nodes, {len(add_edges)} edges")

    found      = has_parallel
    confidence = 0.85 if (found and has_fan_in) else (0.55 if found else 0.70)

    return Evidence(
        goal="Verify parallel fan-out/fan-in graph (Detectives + Judges run concurrently)",
        found=found,
        content="\n".join(snippets),
        location=", ".join(f for f, _ in graph_files[:3]),
        rationale=(
            f"Fan-out detected: {has_parallel}. Fan-in sync detected: {has_fan_in}."
        ),
        confidence=confidence,
        tags=["langgraph", "parallel" if has_parallel else "linear",
              "fan-in" if has_fan_in else "no-fan-in"],
    )


# ─────────────────────────────────────────────
#  FORENSIC PROTOCOL C — TOOL SANDBOXING
# ─────────────────────────────────────────────

def analyze_tool_sandboxing(repo_path: str) -> Evidence:
    """
    Verify git clone uses tempfile + subprocess, not raw os.system.
    """
    tools_dir = os.path.join(repo_path, "src", "tools")
    if not os.path.exists(tools_dir):
        tools_dir = repo_path

    uses_tempfile    = False
    uses_os_system   = False
    uses_subprocess  = False
    has_error_handling = False
    snippet          = ""
    location         = tools_dir

    for fpath in scan_directory_for_python(tools_dir):
        v = parse_python_file(fpath)
        if not v:
            continue

        imp_str   = " ".join(v.imports)
        calls_str = " ".join(v.function_calls)

        if "tempfile" in imp_str:
            uses_tempfile = True
            location = fpath

        if "os.system" in calls_str:
            uses_os_system = True

        if "subprocess" in imp_str:
            uses_subprocess = True

        try:
            raw = Path(fpath).read_text(errors="replace")
            if "TemporaryDirectory" in raw:
                uses_tempfile = True
                snippet = "TemporaryDirectory confirmed"
                location = fpath
            if "try:" in raw and "except" in raw:
                has_error_handling = True
        except Exception:
            pass

    is_secure = uses_tempfile and not uses_os_system and has_error_handling
    confidence = 0.92 if is_secure else (0.30 if uses_os_system else 0.55)

    charges = []
    if uses_os_system:
        charges.append("Security Negligence: raw os.system detected")
    if not uses_tempfile:
        charges.append("No tempfile sandboxing found")

    return Evidence(
        goal="Verify sandboxed git clone with tempfile.TemporaryDirectory and error handling",
        found=is_secure,
        content=snippet or (
            f"tempfile={uses_tempfile}, os.system={uses_os_system}, "
            f"subprocess={uses_subprocess}, try/except={has_error_handling}"
        ),
        location=location,
        rationale=(
            f"Security: tempfile={uses_tempfile}, os.system={uses_os_system} "
            f"(BAD if True), error_handling={has_error_handling}. "
            + (f"Charges: {charges}" if charges else "No violations.")
        ),
        confidence=confidence,
        tags=["security", "sandboxing"] + (["violation"] if charges else ["compliant"]),
    )


# ─────────────────────────────────────────────
#  FORENSIC PROTOCOL D — STRUCTURED OUTPUT
# ─────────────────────────────────────────────

def analyze_structured_output(repo_path: str) -> Evidence:
    """
    Confirm Judge LLMs use .with_structured_output() or .bind_tools()
    bound to the JudicialOpinion Pydantic schema.
    """
    candidates = [
        os.path.join(repo_path, "src", "nodes", "judges.py"),
        os.path.join(repo_path, "src", "judges.py"),
        os.path.join(repo_path, "judges.py"),
    ]

    found_structured      = False
    found_pydantic_binding = False
    found_retry           = False
    snippet               = ""
    location              = "src/nodes/judges.py (not found)"

    for fpath in candidates:
        if not os.path.exists(fpath):
            continue
        location = fpath
        raw = Path(fpath).read_text(errors="replace")

        if "with_structured_output" in raw:
            found_structured = True
            snippet += "with_structured_output() found\n"
        if "bind_tools" in raw:
            found_structured = True
            snippet += "bind_tools() found\n"
        if "JudicialOpinion" in raw or "BaseModel" in raw:
            found_pydantic_binding = True
        if "retry" in raw.lower() or ("for attempt" in raw and "range" in raw):
            found_retry = True
        break  # Use the first matching file

    # Fallback: scan whole repo
    if not found_structured:
        for fpath in scan_directory_for_python(repo_path):
            raw = Path(fpath).read_text(errors="replace")
            if "with_structured_output" in raw or "bind_tools" in raw:
                found_structured = True
                location = fpath
                snippet = f"Found in {os.path.relpath(fpath, repo_path)}"
                break

    confidence = 0.92 if (found_structured and found_pydantic_binding and found_retry) \
        else (0.65 if (found_structured and found_pydantic_binding) else (0.40 if found_structured else 0.10))

    return Evidence(
        goal="Verify Judge LLMs use .with_structured_output(JudicialOpinion) with retry logic",
        found=found_structured,
        content=snippet.strip() or "No structured output enforcement found",
        location=location,
        rationale=(
            f"Structured output enforced: {found_structured}. "
            f"Pydantic schema binding: {found_pydantic_binding}. "
            f"Retry logic present: {found_retry}."
        ),
        confidence=confidence,
        tags=(["structured-output", "pydantic-binding"] + (["retry"] if found_retry else []))
              if found_structured else ["free-text", "hallucination-risk"],
    )


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _error_evidence(goal: str, location: str, rationale: str, content: str) -> Evidence:
    return Evidence(
        goal=goal, found=False, content=content, location=location,
        rationale=rationale, confidence=0.0, tags=["error"],
    )