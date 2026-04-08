# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

12345 Government Services Hotline Intelligent Customer Service System — a multi-agent system built on **DeepAgents** framework with LangGraph. Routes citizen requests through intent classification into complaint, inquiry, or suggestion sub-agents.

## Commands

```bash
# Run tests
pytest tests/ -v

# Run a single test file
pytest tests/test_complaint_tracker.py -v

# CLI single message
python main.py --message "我家停水了"

# CLI interactive mode
python main.py --interactive

# FastAPI web service
python main.py --serve --host 0.0.0.0 --port 8080

# Gradio web UI
python main.py --gradio --host 0.0.0.0 --port 8080
```

## Architecture

**Supervisor → Sub-agent routing pattern:**

```
User Input (CLI / FastAPI / Gradio)
    ↓
Supervisor Agent (main.py + AGENTS.md)
    ↓ intent classification
    ├── Complaint Agent (agents/complaint/) → element collection → ticket submission
    ├── Inquiry Agent (agents/inquiry/) → knowledge base query → response
    ├── Suggestion Agent (agents/suggestion/) → summarize → warm response
    └── Element Extraction Agent (agents/element_extraction/) → validation
```

- **main.py** — Entry point. Creates supervisor agent, defines sub-agent specs (`_complaint_subagent_spec()`, etc.), and exposes CLI/FastAPI/Gradio interfaces.
- **AGENTS.md** — Supervisor system prompt with intent classification rules, context-switch handling, and multi-complaint policies.
- **agents/*/AGENTS.md** — Sub-agent system prompts defining behavior rules per agent type.
- **skills/*/SKILL.md** — Reusable skill definitions (intent classification, complaint type mapping, empathy response, etc.).

**Tools (tools/):**
- `knowledge_base.py` — KB query with mock/real mode and fallback.
- `ticket_api.py` — Ticket submission with required element validation; falls back to local JSON storage.
- `session_store.py` — `SessionStackManager` for multi-task stacking with `interrupt_depth` guard (max 2).

**State tracking (utils/):**
- `complaint_tracker.py` — `ComplaintTracker` manages multiple complaints per session, generates status summaries for LLM context. Delegates element-collected judgment to LLM rather than rigid state tracking.
- `response_guard.py` — Enforces single-question-per-turn rule by truncating multi-question responses.

## Key Design Decisions

- **LLM-based element judgment** — The complaint tracker shows checklists of required elements but delegates "is this element collected?" judgment to the LLM via conversation context, rather than programmatic state tracking. This prevents repetitive questioning loops.
- **Mock mode** — Set `MOCK_SERVICES=true` in `.env` for offline development. Tools provide built-in responses without external services.
- **Complaint schemas** — Defined in `data/complaint_schemas.json` with 6 types (WATER_OUTAGE, POWER_OUTAGE, NOISE_COMPLAINT, ROAD_DAMAGE, GAS_ISSUE, OTHER), each specifying required/optional elements with validation rules.

## Configuration

- `.env` — LLM connection (base URL, model, API key), mock mode toggle, service endpoints, LangSmith tracing.
- `data/complaint_schemas.json` — Complaint type definitions with required elements.
- `data/intent_keywords.json` — Keyword-based intent classification reference.

## Testing Patterns

- Tests use `unittest.mock` extensively to stub deepagents/langchain dependencies.
- `test_complaint_tracker.py` covers single/multi-complaint state transitions and summary generation.
- `test_response_guard.py` validates question truncation and element reminder injection.
- `test_tools.py` covers both mock and real tool modes.
