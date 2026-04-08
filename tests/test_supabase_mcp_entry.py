import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "supabase_mcp_entry.py"


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("SUPABASE_ACCESS_TOKEN", None)
    env.pop("SUPABASE_MCP_ENTRYPOINT", None)
    return env


def test_supabase_mcp_entry_fails_fast_without_access_token():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--version"],
        cwd=ROOT,
        env=_base_env(),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "SUPABASE_ACCESS_TOKEN" in result.stderr


def test_supabase_mcp_entry_executes_override_entrypoint():
    env = _base_env()
    env["SUPABASE_ACCESS_TOKEN"] = "test-token"
    env["SUPABASE_MCP_ENTRYPOINT"] = sys.executable

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "-c", "print('override-ok')"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "override-ok"


def test_supabase_mcp_entry_finds_cached_server_for_version():
    env = _base_env()
    env["SUPABASE_ACCESS_TOKEN"] = "test-token"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--version"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert re.fullmatch(r"\d+\.\d+\.\d+", result.stdout.strip())
