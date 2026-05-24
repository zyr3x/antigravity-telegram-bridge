#!/usr/bin/env python3
"""
Telegram Inbox — Fetch unread messages for Antigravity agents.

Retrieves new messages sent to the bot by admin users via Telegram's
getUpdates API with offset tracking.  The agent calls this script to
"check its inbox", processes each message with its tools, and replies
through tg_send.py.

Supports: text messages, captions, photos, documents, voice, video,
audio, stickers, and callback queries. Files are downloaded to the
uploads directory (default: <project_root>/tmp/uploads/).

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
    python3 tg_inbox.py --uploads-dir /path/to/uploads
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse
import tg_utils


# ---------------------------------------------------------------------------
# Project Root Resolution
# ---------------------------------------------------------------------------

def _find_project_root(explicit_env_path=None):
    """Return the directory containing .env (project root)."""
    env_path = tg_utils._find_env_file(explicit_env_path)
    if env_path:
        return os.path.dirname(env_path)
    return os.getcwd()


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
        "allowed_updates": json.dumps(["message", "callback_query"]),
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
# File download helpers
# ---------------------------------------------------------------------------

def _get_file_path(token, file_id):
    """Call getFile to get the server-side file path for downloading."""
    url = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data["result"].get("file_path")
    except Exception as exc:
        print(f"getFile error for {file_id}: {exc}", file=sys.stderr)
    return None


def _download_file(token, server_file_path, local_path):
    """Download a file from Telegram servers to a local path."""
    url = f"https://api.telegram.org/file/bot{token}/{server_file_path}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            with open(local_path, "wb") as f:
                f.write(resp.read())
        return True
    except Exception as exc:
        print(f"Download error: {exc}", file=sys.stderr)
        return False


def _extract_file_info(msg):
    """Extract file_id, file_name, and file_type from a message.

    Returns (file_id, file_name, file_type) or (None, None, None).
    """
    # Photo — array of PhotoSize, pick the largest (last)
    if "photo" in msg:
        photos = msg["photo"]
        largest = photos[-1]  # last = highest resolution
        return largest["file_id"], None, "photo"

    # Document
    if "document" in msg:
        doc = msg["document"]
        return doc["file_id"], doc.get("file_name"), "document"

    # Voice
    if "voice" in msg:
        return msg["voice"]["file_id"], None, "voice"

    # Audio
    if "audio" in msg:
        audio = msg["audio"]
        name = audio.get("file_name") or audio.get("title")
        return audio["file_id"], name, "audio"

    # Video
    if "video" in msg:
        video = msg["video"]
        return video["file_id"], video.get("file_name"), "video"

    # Video note (round video)
    if "video_note" in msg:
        return msg["video_note"]["file_id"], None, "video_note"

    # Sticker
    if "sticker" in msg:
        return msg["sticker"]["file_id"], None, "sticker"

    return None, None, None


def download_attachment(token, msg, uploads_dir):
    """Download any file attachment from a message.

    Returns (local_file_path, file_type) or (None, None).
    """
    file_id, file_name, file_type = _extract_file_info(msg)
    if not file_id:
        return None, None

    # Get server-side file path
    server_path = _get_file_path(token, file_id)
    if not server_path:
        return None, None

    # Build local filename
    if file_name:
        local_name = file_name
    else:
        # Use server path's extension (e.g., photos/file_123.jpg)
        ext = os.path.splitext(server_path)[1] or ".bin"
        local_name = f"{file_type}_{file_id[:16]}{ext}"

    # Ensure uploads directory exists
    os.makedirs(uploads_dir, exist_ok=True)

    local_path = os.path.join(uploads_dir, local_name)

    # Avoid overwriting — append counter if file exists
    if os.path.exists(local_path):
        base, ext = os.path.splitext(local_path)
        counter = 1
        while os.path.exists(f"{base}_{counter}{ext}"):
            counter += 1
        local_path = f"{base}_{counter}{ext}"

    if _download_file(token, server_path, local_path):
        return local_path, file_type

    return None, None


# ---------------------------------------------------------------------------
# Message filtering & formatting
# ---------------------------------------------------------------------------

def filter_admin_messages(updates, admin_ids, token=None, uploads_dir=None):
    """Keep text messages and callback queries from authorised admin users.

    If token and uploads_dir are provided, downloads file attachments.
    """
    messages = []
    for update in updates:
        # Handle regular messages
        msg = update.get("message")
        if msg:
            sender = msg.get("from", {})
            sender_id = str(sender.get("id", ""))
            if sender_id not in admin_ids:
                continue

            text = msg.get("text", "") or msg.get("caption", "")

            # Try to download any file attachment
            file_path = None
            file_type = None
            if token and uploads_dir:
                file_path, file_type = download_attachment(token, msg, uploads_dir)

            # Accept message if it has text OR a file
            if text or file_path:
                item = {
                    "update_id": update["update_id"],
                    "from_id": sender_id,
                    "from_name": sender.get("first_name", "User"),
                    "chat_id": msg["chat"]["id"],
                    "date": msg.get("date", 0),
                    "text": text,
                    "type": "message",
                }
                if file_path:
                    item["file_path"] = file_path
                    item["file_type"] = file_type
                if "message_thread_id" in msg:
                    item["thread_id"] = msg["message_thread_id"]
                messages.append(item)
            continue

        # Handle callback queries
        cbq = update.get("callback_query")
        if cbq:
            sender = cbq.get("from", {})
            sender_id = str(sender.get("id", ""))
            if sender_id not in admin_ids:
                continue

            data = cbq.get("data", "")
            msg_obj = cbq.get("message", {})
            if data:
                item = {
                    "update_id": update["update_id"],
                    "from_id": sender_id,
                    "from_name": sender.get("first_name", "User"),
                    "chat_id": msg_obj.get("chat", {}).get("id", ""),
                    "date": msg_obj.get("date", 0),
                    "text": data,
                    "type": "callback_query",
                    "callback_id": cbq.get("id", "")
                }
                if "message_thread_id" in msg_obj:
                    item["thread_id"] = msg_obj["message_thread_id"]
                messages.append(item)

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
    parser.add_argument(
        "--uploads-dir",
        default=None,
        help="Directory to save downloaded files (default: <project_root>/tmp/uploads).",
    )
    args = parser.parse_args()

    # ---- Configuration -------------------------------------------------------
    tg_utils.load_dotenv(args.env_file)

    token = tg_utils.get_token()
    admin_ids = tg_utils.get_admin_ids(as_set=True)

    if not token or not admin_ids:
        # Telegram not configured — return empty inbox, no error
        print(json.dumps([], ensure_ascii=False))
        sys.exit(0)

    # ---- Resolve uploads directory -------------------------------------------
    uploads_dir = (
        args.uploads_dir
        or os.environ.get("TG_UPLOADS_DIR")
        or os.path.join(_find_project_root(args.env_file), ".telegram_uploads")
    )

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
    messages = filter_admin_messages(updates, admin_ids, token=token, uploads_dir=uploads_dir)
    print(json.dumps(messages, ensure_ascii=False, indent=2))

    # ---- Advance offset (unless --peek) --------------------------------------
    if not args.peek and updates:
        save_offset(new_offset, args.env_file)

    sys.exit(0)


if __name__ == "__main__":
    main()
