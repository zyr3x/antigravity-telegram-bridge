#!/usr/bin/env python3
"""
Telegram Inbox — Fetch unread messages for Antigravity agents.

Retrieves new messages sent to the bot by admin users via Telegram's
getUpdates API with offset tracking.  The agent calls this script to
"check its inbox", processes each message with its tools, and replies
through tg_send.py.

Offset persistence:
    The last-seen update_id (+1) is stored in .telegram_offset so that
    each invocation only returns genuinely NEW messages.

Exit codes:
    0 — success (messages printed as JSON to stdout)
    2 — configuration error

Usage:
    python3 tg_inbox.py                # fetch new messages
    python3 tg_inbox.py --peek         # fetch without advancing offset
    python3 tg_inbox.py --mark-read    # advance offset without printing
    python3 tg_inbox.py --env-file /path/to/.env   # explicit .env path
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse


# ---------------------------------------------------------------------------
# .env resolution — CWD-first strategy (works for global plugins)
# ---------------------------------------------------------------------------

def _find_env_file(explicit_path=None):
    """Find the .env file using a priority-based resolution strategy.

    Order:
      1. Explicit path (--env-file flag)
      2. Current working directory
      3. Walk upward from CWD
    """
    # 1. Explicit path
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        print(f"Warning: --env-file path not found: {explicit_path}", file=sys.stderr)
        return None

    # 2. CWD
    cwd_env = os.path.join(os.getcwd(), ".env")
    if os.path.isfile(cwd_env):
        return cwd_env

    # 3. Walk upward from CWD
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


def _find_project_root(explicit_env_path=None):
    """Return the directory containing .env (project root)."""
    env_path = _find_env_file(explicit_env_path)
    if env_path:
        return os.path.dirname(env_path)
    return os.getcwd()


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
            if key and key not in os.environ:  # don't override existing
                os.environ[key] = val


def get_token():
    """Get bot token with fallback variable names."""
    return os.environ.get("TG_BOT_TOKEN") or os.environ.get("AGENT_TELEGRAM_BOT_TOKEN")


def get_admin_ids():
    """Get admin IDs with fallback variable names. Returns a set of strings."""
    raw = os.environ.get("TG_ADMIN_IDS") or os.environ.get("TELEGRAM_ADMIN_IDS")
    if not raw:
        return set()
    return {aid.strip() for aid in raw.split(",") if aid.strip()}


# ---------------------------------------------------------------------------
# Offset persistence
# ---------------------------------------------------------------------------

OFFSET_FILENAME = ".telegram_offset"


def _offset_path(explicit_env_path=None):
    return os.path.join(_find_project_root(explicit_env_path), OFFSET_FILENAME)


def load_offset(explicit_env_path=None):
    """Load the last-seen update_id (+1) from disk. Returns 0 if none."""
    path = _offset_path(explicit_env_path)
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return int(f.read().strip())
        except (ValueError, OSError):
            pass
    return 0


def save_offset(offset, explicit_env_path=None):
    """Persist the next offset to disk."""
    path = _offset_path(explicit_env_path)
    with open(path, "w") as f:
        f.write(str(offset))


# ---------------------------------------------------------------------------
# Telegram getUpdates (stdlib only — no `requests` dependency)
# ---------------------------------------------------------------------------

def get_updates(token, offset=0, timeout=1):
    """Call getUpdates and return the list of Update objects."""
    params = {
        "timeout": str(timeout),
        "allowed_updates": json.dumps(["message"]),
    }
    if offset:
        params["offset"] = str(offset)

    url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data.get("result", [])
            else:
                print(f"Telegram API error: {data}", file=sys.stderr)
                return []
    except Exception as exc:
        print(f"Request error: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Message filtering & formatting
# ---------------------------------------------------------------------------

def filter_admin_messages(updates, admin_ids):
    """Keep only text messages from authorised admin users."""
    messages = []
    for update in updates:
        msg = update.get("message")
        if not msg:
            continue
        sender = msg.get("from", {})
        sender_id = str(sender.get("id", ""))
        if sender_id not in admin_ids:
            continue
        text = msg.get("text", "")
        if not text:
            continue
        messages.append({
            "update_id": update["update_id"],
            "from_id": sender_id,
            "from_name": sender.get("first_name", "User"),
            "chat_id": msg["chat"]["id"],
            "date": msg.get("date", 0),
            "text": text,
        })
    return messages


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch unread Telegram messages for an Antigravity agent.",
    )
    parser.add_argument(
        "--peek",
        action="store_true",
        help="Fetch messages without advancing the offset (re-readable).",
    )
    parser.add_argument(
        "--mark-read",
        action="store_true",
        help="Advance offset to skip all pending messages (no output).",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Explicit path to .env file (overrides auto-detection).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1,
        help="Long-polling timeout in seconds (default: 1).",
    )
    args = parser.parse_args()

    # ---- Configuration -------------------------------------------------------
    load_dotenv(args.env_file)

    token = get_token()
    admin_ids = get_admin_ids()

    if not token or not admin_ids:
        # Telegram not configured — return empty inbox, no error
        print(json.dumps([], ensure_ascii=False))
        sys.exit(0)

    # ---- Fetch updates -------------------------------------------------------
    offset = load_offset(args.env_file)
    updates = get_updates(token, offset=offset, timeout=args.timeout)

    if not updates:
        print(json.dumps([], ensure_ascii=False))
        sys.exit(0)

    # ---- Compute new offset --------------------------------------------------
    max_update_id = max(u["update_id"] for u in updates)
    new_offset = max_update_id + 1

    # ---- Mark-read mode: just advance offset ---------------------------------
    if args.mark_read:
        save_offset(new_offset, args.env_file)
        print(f"Offset advanced to {new_offset}, {len(updates)} update(s) skipped.")
        sys.exit(0)

    # ---- Filter & print messages ---------------------------------------------
    messages = filter_admin_messages(updates, admin_ids)
    print(json.dumps(messages, ensure_ascii=False, indent=2))

    # ---- Advance offset (unless --peek) --------------------------------------
    if not args.peek and messages:
        save_offset(new_offset, args.env_file)

    sys.exit(0)


if __name__ == "__main__":
    main()
