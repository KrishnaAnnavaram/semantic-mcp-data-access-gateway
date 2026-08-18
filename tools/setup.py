"""One-command bootstrap: fresh clone -> verified database -> running gateway.

This replaces the two pipeline agents that used to drive setup. Standing the
database up is a scripted, verifiable sequence with one correct answer, so it
belongs in a script that always does the same thing — not in an agent that
reasons about it afresh each time.

    python tools/setup.py              # full bootstrap
    python tools/setup.py --check      # report state, change nothing
    python tools/setup.py --skip-data  # infra + schema only, no 4-minute download

Every step is idempotent: re-running a completed step is a no-op, so an
interrupted run is resumed by running it again. Narrative guide, including what
to do when a step fails: docs/postgres-setup.md
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def say(symbol: str, colour: str, message: str) -> None:
    print(f"{colour}{symbol}{RESET} {message}", flush=True)


def ok(m): say("OK  ", GREEN, m)
def warn(m): say("WARN", YELLOW, m)
def fail(m): say("FAIL", RED, m)
def step(n, total, m): print(f"\n{DIM}[{n}/{total}]{RESET} {m}", flush=True)


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO_ROOT, text=True,
                          capture_output=capture, check=False)


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


# -- checks -------------------------------------------------------------------

def check_prerequisites() -> bool:
    good = True
    if sys.version_info < (3, 11):
        fail(f"Python 3.11+ required, found {sys.version.split()[0]}")
        good = False
    else:
        ok(f"Python {sys.version.split()[0]}")

    if not have("docker"):
        fail("docker not found on PATH — install Docker Desktop")
        good = False
    else:
        r = run(["docker", "info"], capture=True)
        if r.returncode != 0:
            fail("Docker is installed but not running — start Docker Desktop")
            good = False
        else:
            ok("Docker running")
    return good


def check_env() -> bool:
    """Create .env from the example, but never overwrite a real one."""
    env, example = REPO_ROOT / ".env", REPO_ROOT / ".env.example"
    if env.exists():
        ok(".env present")
    elif example.exists():
        shutil.copy(example, env)
        warn(".env created from .env.example — edit it and set real passwords")
        warn("  POSTGRES_PASSWORD, MCP_READER_PASSWORD, ANTHROPIC_API_KEY")
        return False  # deliberately stop: defaults must not be used silently
    else:
        fail("neither .env nor .env.example found")
        return False

    frontend_env = REPO_ROOT / "frontend" / ".env"
    if not frontend_env.exists() and (REPO_ROOT / "frontend" / ".env.example").exists():
        shutil.copy(REPO_ROOT / "frontend" / ".env.example", frontend_env)
        text = frontend_env.read_text(encoding="utf-8").replace(
            "VITE_AGENT_BACKEND=mock", "VITE_AGENT_BACKEND=rest").replace(
            "VITE_AGENT_TIMEOUT_SECONDS=60", "VITE_AGENT_TIMEOUT_SECONDS=180")
        frontend_env.write_text(text, encoding="utf-8")
        ok("frontend/.env created (VITE_AGENT_BACKEND=rest, 180s timeout)")
    return True


def wait_for_postgres(timeout_s: int = 90) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = run(["docker", "compose", "exec", "-T", "postgres",
                 "pg_isready", "-U", os.environ.get("POSTGRES_USER", "gateway")],
                capture=True)
        if r.returncode == 0:
            return True
        time.sleep(2)
    return False


# -- steps --------------------------------------------------------------------

def install_dependencies() -> bool:
    for args, label in (
        (["-r", "requirements.txt"], "requirements.txt"),
        (["-e", "./llm", "-e", "./postgres", "-e", "./mcp", "-e", "./backend",
          "-e", "./agents"], "five packages (editable)"),
    ):
        r = run([sys.executable, "-m", "pip", "install", "-q", *args], capture=True)
        if r.returncode != 0:
            fail(f"pip install {label} failed:\n{r.stderr[-800:]}")
            return False
        ok(f"installed {label}")
    return True


def start_containers() -> bool:
    r = run(["docker", "compose", "up", "-d", "postgres", "qdrant"], capture=True)
    if r.returncode != 0:
        fail(f"docker compose up failed:\n{r.stderr[-800:]}")
        return False
    ok("postgres + qdrant started")
    if not wait_for_postgres():
        fail("postgres did not become ready within 90s")
        return False
    ok("postgres accepting connections")
    return True


def module(name: str, *args: str, label: str) -> bool:
    r = run([sys.executable, "-m", name, *args])
    if r.returncode != 0:
        fail(f"{label} failed (exit {r.returncode})")
        return False
    ok(label)
    return True


def script(path: str, *args: str, label: str) -> bool:
    r = run([sys.executable, path, *args])
    if r.returncode != 0:
        fail(f"{label} failed (exit {r.returncode})")
        return False
    ok(label)
    return True


def data_already_present() -> bool:
    raw = REPO_ROOT / "data" / "raw"
    return raw.exists() and any(raw.rglob("*.xml"))


# -- entry --------------------------------------------------------------------

def report_state() -> int:
    print("Environment")
    check_prerequisites()
    print()
    print("Repository")
    ok(".env present") if (REPO_ROOT / ".env").exists() else warn(".env missing")
    (ok if data_already_present() else warn)(
        f"raw Treasury files: {len(list((REPO_ROOT / 'data' / 'raw').rglob('*.xml'))) if (REPO_ROOT / 'data' / 'raw').exists() else 0}")
    try:
        import backend, mcp_servers, treasury_db  # noqa: F401
        ok("backend, mcp_servers, treasury_db importable")
    except ImportError as exc:
        warn(f"packages not importable ({exc.name}) — run:"
             " pip install -e ./llm -e ./postgres -e ./mcp -e ./backend -e ./agents")
    print()
    print("Database")
    run([sys.executable, "-m", "treasury_db.migrate", "--status"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="report state and change nothing")
    parser.add_argument("--skip-data", action="store_true",
                        help="skip the Treasury download (~4 min, ~60 MB)")
    parser.add_argument("--skip-knowledge", action="store_true",
                        help="skip Qdrant ingestion of knowledge/")
    args = parser.parse_args()

    if args.check:
        return report_state()

    print("=" * 74)
    print("semantic-mcp-data-access-gateway — setup")
    print("=" * 74)

    total = 7
    step(1, total, "Prerequisites")
    if not check_prerequisites():
        return 1

    step(2, total, "Configuration")
    if not check_env():
        print("\nEdit .env, then run this script again.")
        return 1

    step(3, total, "Dependencies")
    if not install_dependencies():
        return 1

    step(4, total, "Containers")
    if not start_containers():
        return 1

    step(5, total, "Source data")
    if args.skip_data:
        warn("skipped (--skip-data)")
    elif data_already_present():
        ok("raw Treasury files already on disk — skipping download")
    elif not script("data/acquisition/download_us_treasury.py",
                    label="downloaded Treasury source data"):
        return 1

    step(6, total, "Schema, load, verify")
    if not module("treasury_db.migrate", label="migrations applied"):
        return 1
    if not args.skip_data:
        if not module("treasury_db.load", label="data loaded"):
            return 1
        if not script("tools/verify_load.py", "--self-test", label="load verified"):
            return 1
    if not module("mcp_servers.data.bootstrap", label="mcp_reader password set"):
        return 1

    step(7, total, "Knowledge base")
    if args.skip_knowledge:
        warn("skipped (--skip-knowledge)")
    else:
        r = run([sys.executable, "-c",
                 "from backend.knowledge.knowledge_base import KnowledgeBase;"
                 " KnowledgeBase(rebuild=True)"])
        (ok if r.returncode == 0 else warn)(
            "knowledge ingested into Qdrant" if r.returncode == 0
            else "knowledge ingestion failed — re-run it after checking QDRANT_URL")

    print("\n" + "=" * 74)
    ok("Setup complete")
    print("""
Verify the whole stack:
    python tools/verify_load.py --self-test      74/74
    python tools/verify_mcp.py --self-test       35/35
    python -m mcp_servers.host --demo                end-to-end chain
    pytest                                       56 tests

Run it:
    python -m backend.api.service                API   on :8000
    cd frontend && npm install && npm run dev    UI    on :5173

ANTHROPIC_API_KEY must be set in .env before the agent will answer.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
