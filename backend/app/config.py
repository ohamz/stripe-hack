"""Environment configuration and key validation.

Loaded before anything imports cognee, because cognee reads its settings from the
environment at import time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEMO_DATA_DIR = REPO_ROOT / "demo_data"
VAR_DIR = BACKEND_DIR / "var"

ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
    # Cognee searches for .env only up to the nearest pyproject.toml (backend/),
    # so point it at the repo-root .env explicitly.
    os.environ.setdefault("COGNEE_ENV_FILE", str(ENV_FILE))

# Keep Cognee's local stores inside the backend folder so `make reset` is self-contained.
os.environ.setdefault("DATA_ROOT_DIRECTORY", str(BACKEND_DIR / ".cognee" / "data"))
os.environ.setdefault("SYSTEM_ROOT_DIRECTORY", str(BACKEND_DIR / ".cognee" / "system"))
os.environ.setdefault("TELEMETRY_DISABLED", "1")
# Cognee recall skill: AUTO_FEEDBACK adds one extra LLM call per answered recall; the skill gate can append
# unrelated "skills" results to procedural-sounding questions. Tab needs neither. Both overridable in .env.
os.environ.setdefault("AUTO_FEEDBACK", "false")
os.environ.setdefault("SKILL_GATE_ENABLED", "false")

# Values people commonly leave in .env before adding a real key.
_PLACEHOLDER_MARKERS = ("xxx", "...", "your", "changeme", "replace", "<", "placeholder")


class ConfigError(RuntimeError):
    """Raised when the configuration is unsafe to start with (for example a live Stripe key)."""


@dataclass(frozen=True)
class KeyStatus:
    ok: bool
    state: str  # "ok" | "missing" | "placeholder" | "live_key_refused" | "wrong_format"
    message: str


def _looks_like_placeholder(value: str, min_len: int) -> bool:
    low = value.lower()
    return len(value) < min_len or any(m in low for m in _PLACEHOLDER_MARKERS)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip().strip('"').strip("'")


def llm_key_status() -> KeyStatus:
    value = _env("LLM_API_KEY")
    if not value:
        return KeyStatus(False, "missing", "LLM key missing: set LLM_API_KEY in .env")
    if _looks_like_placeholder(value, 20):
        return KeyStatus(False, "placeholder", "LLM key missing: LLM_API_KEY in .env looks like a placeholder")
    return KeyStatus(True, "ok", "LLM key configured")


def stripe_key_status() -> KeyStatus:
    value = _env("STRIPE_SECRET_KEY")
    if not value:
        return KeyStatus(False, "missing", "Stripe key missing: set STRIPE_SECRET_KEY (sk_test_...) in .env. Billing is disabled.")
    if not value.startswith("sk_test_"):
        if value.startswith(("sk_live_", "rk_live_")):
            return KeyStatus(False, "live_key_refused", "Refusing to start: STRIPE_SECRET_KEY is a live key. Tab only runs in Stripe test mode (sk_test_...).")
        return KeyStatus(False, "wrong_format", "Refusing to start: STRIPE_SECRET_KEY must start with sk_test_ (Stripe test mode only).")
    if _looks_like_placeholder(value, 30):
        return KeyStatus(False, "placeholder", "Stripe key missing: STRIPE_SECRET_KEY in .env looks like a placeholder. Billing is disabled.")
    return KeyStatus(True, "ok", "Stripe test mode key configured")


def assert_safe_to_start() -> None:
    """Refuse to start with any Stripe key that isn't a test key. An empty key only disables billing."""
    status = stripe_key_status()
    if status.state in ("live_key_refused", "wrong_format"):
        raise ConfigError(status.message)


@dataclass(frozen=True)
class Settings:
    public_base_url: str
    database_url: str
    demo_mode: bool
    stripe_secret_key: str
    stripe_webhook_secret: str
    slack_bot_token: str
    slack_channel_ids: list[str]
    imap_host: str
    imap_user: str
    imap_password: str


def _database_url() -> str:
    url = _env("DATABASE_URL") or "sqlite:///./tab.db"
    # Resolve the relative SQLite path against backend/, whatever the working directory is.
    if url.startswith("sqlite:///./"):
        url = "sqlite:///" + str(BACKEND_DIR / url[len("sqlite:///./"):])
    return url


def get_settings() -> Settings:
    return Settings(
        public_base_url=(_env("PUBLIC_BASE_URL") or "http://localhost:5173").rstrip("/"),
        database_url=_database_url(),
        demo_mode=_env("DEMO_MODE").lower() in ("1", "true", "yes", ""),
        stripe_secret_key=_env("STRIPE_SECRET_KEY"),
        stripe_webhook_secret=_env("STRIPE_WEBHOOK_SECRET"),
        slack_bot_token=_env("SLACK_BOT_TOKEN"),
        slack_channel_ids=[c.strip() for c in _env("SLACK_CHANNEL_IDS").split(",") if c.strip()],
        imap_host=_env("IMAP_HOST"),
        imap_user=_env("IMAP_USER"),
        imap_password=_env("IMAP_PASSWORD"),
    )
