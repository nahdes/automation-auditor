# 🏛 Automaton Auditor

Hierarchical LangGraph Agent Swarm for Autonomous Code Auditing

## Features

- **Three-Layer Architecture**: Detectives → Judges → Chief Justice
- **Parallel Execution**: Fan-out/fan-in graph topology
- **AST-Based Analysis**: Robust code parsing (no regex)
- **Sandboxed Tools**: Secure git operations with tempfile
- **Structured Output**: Pydantic validation throughout
- **LangSmith Tracing**: Full observability

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/yourusername/automaton-auditor.git
cd automaton-auditor

# 2. Setup environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e .

# 4. Configure API keys
cp .env.example .env
nano .env  # Add your OPENAI_API_KEY

# 5. Run audit
python -m src.graph https://github.com/user/repo.git reports/final_report.pdf peer
```
