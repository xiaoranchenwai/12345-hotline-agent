"""Stable entrypoint for the Supabase MCP server in this workspace.

This wrapper avoids `bunx ...@latest` at runtime, which is fragile in the
Codex sandbox. It prefers a cached npm copy of the server and fails fast with
clear diagnostics when the required access token is missing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_GLOB = ".npm/_npx/*/node_modules/@supabase/mcp-server-supabase/dist/transports/stdio.js"


def _load_env_file(env: dict[str, str], env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return env

    merged = dict(env)
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        merged.setdefault(key, value)
    return merged


def _resolve_cached_entrypoint() -> Path | None:
    candidates = sorted(
        Path.home().glob(DEFAULT_CACHE_GLOB),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _build_command(argv: list[str], env: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    merged_env = _load_env_file(env, ROOT / ".env")
    if not merged_env.get("SUPABASE_ACCESS_TOKEN"):
        raise RuntimeError(
            "SUPABASE_ACCESS_TOKEN is required for the Supabase MCP server. "
            "Set it in your shell environment or add it to the project .env file."
        )

    entrypoint = merged_env.get("SUPABASE_MCP_ENTRYPOINT")
    if entrypoint:
        command = [entrypoint, *argv]
        return command, merged_env

    cached_entrypoint = _resolve_cached_entrypoint()
    if cached_entrypoint is None:
        raise RuntimeError(
            "Supabase MCP package is not cached locally. "
            "Run `npx -y @supabase/mcp-server-supabase@latest --version` once "
            "outside the sandbox, then retry."
        )

    command = ["node", str(cached_entrypoint), *argv]
    return command, merged_env


def main() -> int:
    try:
        command, env = _build_command(sys.argv[1:], os.environ)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    completed = subprocess.run(command, env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
