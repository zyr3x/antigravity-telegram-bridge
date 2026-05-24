#!/usr/bin/env python3
"""
Telegram Text Sender for Antigravity agents.

Sends text messages to all Telegram admin users via the Bot API.
Designed to work as a global plugin — resolves .env from the current
working directory (project root), not from the script's own location.

Exit codes:
    0 — all messages sent successfully (or Telegram not configured — skip)
    1 — partial failure (some recipients failed)
    2 — total failure (no messages sent)

Usage:
    python3 tg_send.py -m "Hello from Antigravity!"
    python3 tg_send.py -m "⚠️ Alert" --level warning
    python3 tg_send.py -m "🔴 Critical" --level critical
    python3 tg_send.py -m "Silent update" --silent
    python3 tg_send.py -m "Message" --env-file /path/to/.env
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse


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
    """Find the .env file using a priority-based resolution strategy."""
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        print(f"Warning: --env-file path not found: {explicit_path}", file=sys.stderr)
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
        return
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


def get_token():
    """Get bot token with fallback variable names."""
    return os.environ.get("TG_BOT_TOKEN") or os.environ.get("AGENT_TELEGRAM_BOT_TOKEN")


def get_admin_ids():
    """Get admin IDs with fallback variable names. Returns a list of strings."""
    raw = os.environ.get("TG_ADMIN_IDS") or os.environ.get("TELEGRAM_ADMIN_IDS")
    if not raw:
        return []
    return [aid.strip() for aid in raw.split(",") if aid.strip()]


# ---------------------------------------------------------------------------
# Telegram helpers (stdlib only — zero dependencies)
# ---------------------------------------------------------------------------

def _post_json(url, payload):
    """POST JSON to a URL. Returns (success, error_msg)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return True, None
                last_error = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
            if e.code == 429:
                # Rate-limited
                try:
                    body = json.loads(e.read().decode("utf-8"))
                    retry_after = body.get("parameters", {}).get("retry_after", BACKOFF_BASE * (2 ** attempt))
                except Exception:
                    retry_after = BACKOFF_BASE * (2 ** attempt)
                time.sleep(retry_after)
                continue
            if e.code >= 500:
                time.sleep(BACKOFF_BASE * (2 ** attempt))
                continue
            return False, last_error
        except urllib.error.URLError as e:
            last_error = f"Connection error: {e.reason}"
            time.sleep(BACKOFF_BASE * (2 ** attempt))
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            time.sleep(BACKOFF_BASE * (2 ** attempt))

    return False, last_error


def send_message(token, chat_id, text, silent=False):
    """Send a text message via sendMessage (HTML parse mode)."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if silent:
        payload["disable_notification"] = True
    return _post_json(url, payload)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Send a Telegram text message to all admin users.",
    )
    parser.add_argument(
        "--message", "-m",
        required=True,
        help="The message text to send.",
    )
    parser.add_argument(
        "--level", "-l",
        choices=["info", "warning", "critical"],
        default=None,
        help="Prepend a coloured emoji prefix to the message.",
    )
    parser.add_argument(
        "--silent", "-s",
        action="store_true",
        default=False,
        help="Send with notifications disabled (silent delivery).",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Explicit path to .env file (overrides auto-detection).",
    )
    args = parser.parse_args()

    # ---- Load configuration --------------------------------------------------
    load_dotenv(args.env_file)

    token = get_token()
    admin_ids = get_admin_ids()

    if not token or not admin_ids:
        print("SKIP: Telegram not configured (TG_BOT_TOKEN or TG_ADMIN_IDS missing). Message not sent.")
        sys.exit(0)

    # ---- Build message text --------------------------------------------------
    text = args.message

    # Convert literal escape sequences from shell
    text = text.replace('\\n', '\n').replace('\\t', '\t')

    if args.level:
        prefix = LEVEL_PREFIXES[args.level]
        if not text.lstrip().startswith(prefix):
            text = f"{prefix} {text}"

    # Auto-silent for info level
    silent = args.silent or (args.level == "info")

    # ---- Send to each admin --------------------------------------------------
    sent_count = 0
    fail_count = 0

    for chat_id in admin_ids:
        ok, err = send_message(token, chat_id, text, silent=silent)
        if ok:
            print(f"✓ Sent to {chat_id}")
            sent_count += 1
        else:
            print(f"✗ Failed for {chat_id}: {err}")
            fail_count += 1

    # ---- Exit code -----------------------------------------------------------
    if fail_count == 0:
        print(f"Done — {sent_count}/{sent_count} delivered.")
        sys.exit(0)
    elif sent_count > 0:
        print(f"Partial — {sent_count}/{sent_count + fail_count} delivered.")
        sys.exit(1)
    else:
        print(f"Failed — 0/{fail_count} delivered.")
        sys.exit(2)


if __name__ == "__main__":
    main()
