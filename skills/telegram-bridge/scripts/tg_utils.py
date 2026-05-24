#!/usr/bin/env python3
"""
Shared utilities for Telegram Bridge scripts.

Provides:
    - .env file resolution and loading
    - Bot token / admin IDs / thread ID helpers
    - JSON POST with exponential backoff and rate-limit handling
    - Common constants (level prefixes, retry config)
"""

import os
import json
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEVEL_PREFIXES = {
    "info": "🔵",
    "warning": "🟡",
    "critical": "🔴",
}

MAX_RETRIES = 3
BACKOFF_BASE = 1  # seconds — retries at 1s, 2s, 4s


# ---------------------------------------------------------------------------
# .env resolution — CWD-first strategy
# ---------------------------------------------------------------------------

def _find_env_file(explicit_path=None):
    """Find the .env file using a priority-based resolution strategy.

    Order:
      1. Explicit path (--env-file flag)
      2. Current working directory
      3. Walk upward from CWD
    """
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        return None

    cwd_env = os.path.join(os.getcwd(), ".env")
    if os.path.isfile(cwd_env):
        return cwd_env

    current = os.getcwd()
    while True:
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
        candidate = os.path.join(current, ".env")
        if os.path.isfile(candidate):
            return candidate

    return None


def load_dotenv(explicit_path=None):
    """Load key=value pairs from .env into os.environ (does NOT override existing)."""
    env_path = _find_env_file(explicit_path)
    if env_path is None:
        return None
    with open(env_path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    return env_path


# ---------------------------------------------------------------------------
# Environment variable helpers
# ---------------------------------------------------------------------------

def get_token():
    """Get bot token with fallback variable names."""
    return os.environ.get("TG_BOT_TOKEN") or os.environ.get("AGENT_TELEGRAM_BOT_TOKEN")


def get_admin_ids(as_set=False):
    """Get admin IDs with fallback variable names.
    
    Returns a list (default) or set of string IDs.
    """
    raw = os.environ.get("TG_ADMIN_IDS") or os.environ.get("TELEGRAM_ADMIN_IDS")
    if not raw:
        return set() if as_set else []
    
    parts = [aid.strip() for aid in raw.split(",") if aid.strip()]
    return set(parts) if as_set else parts


def get_global_thread_id():
    """Get the default thread (topic) ID from environment."""
    return os.environ.get("TG_THREAD_ID")


# ---------------------------------------------------------------------------
# HTTP POST with retries and rate-limit handling
# ---------------------------------------------------------------------------

def post_json(url, payload):
    """POST JSON to a URL with exponential backoff on failures.

    Handles:
      - 429 Too Many Requests (reads retry_after from response)
      - 5xx Server Errors (retries with backoff)
      - Connection errors (retries with backoff)

    Returns:
        (True, response_data_dict) on success
        (False, error_string) on failure
    """
    data = json.dumps(payload).encode("utf-8")
    last_error = None

    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf-8")
                if resp.status == 200:
                    resp_data = json.loads(resp_body)
                    return True, resp_data
                last_error = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            # Read the error body ONCE and store it
            error_body = e.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {e.code}: {error_body}"

            if e.code == 429:
                # Rate-limited — parse retry_after from already-read body
                try:
                    body = json.loads(error_body)
                    retry_after = body.get("parameters", {}).get(
                        "retry_after", BACKOFF_BASE * (2 ** attempt)
                    )
                except Exception:
                    retry_after = BACKOFF_BASE * (2 ** attempt)
                time.sleep(retry_after)
                continue
            if e.code >= 500:
                time.sleep(BACKOFF_BASE * (2 ** attempt))
                continue
            # 4xx (except 429) — don't retry, it's a client error
            return False, last_error
        except urllib.error.URLError as e:
            last_error = f"Connection error: {e.reason}"
            time.sleep(BACKOFF_BASE * (2 ** attempt))
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            time.sleep(BACKOFF_BASE * (2 ** attempt))

    return False, last_error
