"""Tests for agent creation functions in main.py.

Because deepagents (and several other runtime deps) may not be installed in the
test environment, we inject MagicMock stubs into sys.modules for every missing
top-level package *before* main.py is first imported.  This keeps the tests
isolated and dependency-free while still exercising the wiring logic.
"""

import importlib
import sys
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stub_missing(*module_names: str) -> None:
    """Register a MagicMock for each module name that is not already importable."""
    for name in module_names:
        if name not in sys.modules:
            sys.modules[name] = MagicMock()


def _reload_main():
    """Remove main from sys.modules (if present) and re-import it fresh."""
    sys.modules.pop("main", None)
    import main as m
    return m


def _prepare_main_stubs():
    """Inject all stubs required by main.py and return the freshly imported module."""
    _stub_missing(
        "deepagents",
        "deepagents.backends",
        "dotenv",
        "langchain",
        "langchain.chat_models",
        "rich",
        "rich.console",
        "rich.panel",
        "tools",
        "tools.knowledge_base",
        "tools.ticket_api",
    )
    # Ensure dotenv.load_dotenv is callable
    sys.modules["dotenv"].load_dotenv = MagicMock()
    # Ensure rich.console.Console and rich.panel.Panel are classes
    sys.modules["rich.console"].Console = MagicMock
    sys.modules["rich.panel"].Panel = MagicMock
    # tools exports
    sys.modules["tools.knowledge_base"].query_knowledge_base = MagicMock()
    sys.modules["tools.ticket_api"].submit_ticket = MagicMock()
    return _reload_main()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_model_returns_chat_model():
    """create_model should return a langchain chat model."""
    main = _prepare_main_stubs()

    mock_model_instance = MagicMock()
    with patch.object(main, "init_chat_model", return_value=mock_model_instance) as mock_init:
        result = main.create_model()
        mock_init.assert_called_once()
        assert result is mock_model_instance


def test_create_supervisor_agent_returns_agent():
    """create_supervisor_agent should call create_deep_agent with subagent specs."""
    main = _prepare_main_stubs()

    mock_agent = MagicMock()
    with patch.object(main, "create_deep_agent", return_value=mock_agent) as mock_create, \
         patch.object(main, "init_chat_model", return_value=MagicMock()), \
         patch.object(main, "FilesystemBackend", return_value=MagicMock()), \
         patch.object(main, "_read_agent_prompt", return_value="test prompt"):

        agent = main.create_supervisor_agent()
        mock_create.assert_called_once()
        assert agent is mock_agent

        # Verify subagents are passed as dicts with required keys
        call_kwargs = mock_create.call_args
        subagents = call_kwargs.kwargs.get("subagents") or call_kwargs[1].get("subagents", [])
        assert len(subagents) == 3
        for sa in subagents:
            assert isinstance(sa, dict)
            assert "name" in sa
            assert "description" in sa
            assert "system_prompt" in sa


def test_subagent_specs_have_correct_names():
    """All subagent spec functions should return dicts with expected names."""
    main = _prepare_main_stubs()

    with patch.object(main, "_read_agent_prompt", return_value="test prompt"):
        complaint = main._complaint_subagent_spec()
        inquiry = main._inquiry_subagent_spec()
        suggestion = main._suggestion_subagent_spec()
        extraction = main._element_extraction_subagent_spec()

    assert complaint["name"] == "complaint_agent"
    assert inquiry["name"] == "inquiry_agent"
    assert suggestion["name"] == "suggestion_agent"
    assert extraction["name"] == "element_extraction_agent"
