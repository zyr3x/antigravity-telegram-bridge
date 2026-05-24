#!/usr/bin/env python3
"""
Telegram Photo Sender for Antigravity agents.

Sends photos with captions to all Telegram admin users via the Bot API.
Uses multipart/form-data upload via stdlib (no external dependencies).

Exit codes:
    0 — all photos sent successfully (or Telegram not configured — skip)
    1 — partial failure
    2 — total failure

Usage:
    python3 tg_send_photo.py --photo /path/to/image.png --caption "Description"
    python3 tg_send_photo.py --photo /path/to/chart.png --caption "📊 Chart" --level info
    python3 tg_send_photo.py --photo /path/to/img.jpg --caption "Update" --silent
"""

import os
import sys
import json
import time
import uuid
import argparse
import urllib.request
import urllib.error
import tg_utils


# ---------------------------------------------------------------------------
# Multipart form-data builder (stdlib only)
# ---------------------------------------------------------------------------

def _build_multipart(fields, files):
    """Build multipart/form-data body using stdlib.

    Args:
        fields: dict of {name: value} for text fields
        files: dict of {name: (filename, data, content_type)} for file fields

    Returns:
        (body_bytes, content_type_header)
    """
    boundary = f"----AntigravityBridge{uuid.uuid4().hex}"
    parts = []

    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())

    for name, (filename, data, content_type) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(data)
        parts.append(b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


# ---------------------------------------------------------------------------
# Telegram photo sender
# ---------------------------------------------------------------------------

def _guess_content_type(filepath):
    """Guess MIME type from file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return types.get(ext, "application/octet-stream")


def send_photo(token, chat_id, filepath, caption=None, silent=False, thread_id=None, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    
    fields = {"chat_id": str(chat_id)}
    if caption:
        fields["caption"] = caption
    if parse_mode and parse_mode.lower() != "none":
        fields["parse_mode"] = parse_mode
    if silent:
        fields["disable_notification"] = "true"
    if thread_id:
        fields["message_thread_id"] = str(thread_id)

    filename = os.path.basename(filepath)
    content_type = _guess_content_type(filepath)

    with open(filepath, "rb") as f:
        photo_data = f.read()

    files = {"photo": (filename, photo_data, content_type)}
    body, ct_header = _build_multipart(fields, files)

    last_error = None
    for attempt in range(tg_utils.MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": ct_header},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    return True, None
                last_error = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            last_error = f"HTTP {e.code}: {error_body}"
            if e.code == 429:
                try:
                    err_data = json.loads(error_body)
                    retry_after = err_data.get("parameters", {}).get("retry_after", tg_utils.BACKOFF_BASE * (2 ** attempt))
                except Exception:
                    retry_after = tg_utils.BACKOFF_BASE * (2 ** attempt)
                time.sleep(retry_after)
                continue
            if e.code >= 500:
                time.sleep(tg_utils.BACKOFF_BASE * (2 ** attempt))
                continue
            return False, last_error
        except urllib.error.URLError as e:
            last_error = f"Connection error: {e.reason}"
            time.sleep(tg_utils.BACKOFF_BASE * (2 ** attempt))
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            time.sleep(tg_utils.BACKOFF_BASE * (2 ** attempt))

    return False, last_error


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Send a photo via Telegram to all admin users.",
    )
    parser.add_argument(
        "--photo", "-p",
        required=True,
        help="Path to the image file to send.",
    )
    parser.add_argument(
        "--caption", "-c",
        default="",
        help="Caption text for the photo.",
    )
    parser.add_argument(
        "--level", "-l",
        choices=["info", "warning", "critical"],
        default=None,
        help="Prepend a coloured emoji prefix to the caption.",
    )
    parser.add_argument(
        "--silent", "-s",
        action="store_true",
        default=False,
        help="Send with notifications disabled.",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Explicit path to .env file.",
    )
    parser.add_argument(
        "--thread-id", "-t",
        default=None,
        help="Specific thread ID."
    )
    parser.add_argument(
        "--parse-mode",
        default="HTML",
        help="Parse mode (HTML, MarkdownV2, None). Default: HTML."
    )
    args = parser.parse_args()

    # ---- Configuration -------------------------------------------------------
    tg_utils.load_dotenv(args.env_file)

    token = tg_utils.get_token()
    admin_ids = tg_utils.get_admin_ids()

    if not token or not admin_ids:
        print("SKIP: Telegram not configured. Photo not sent.")
        sys.exit(0)

    # ---- Validate photo ------------------------------------------------------
    if not os.path.isfile(args.photo):
        print(f"Error: Photo file not found: {args.photo}", file=sys.stderr)
        sys.exit(2)

    # ---- Build caption -------------------------------------------------------
    caption = args.caption
    if caption:
        caption = caption.replace('\\n', '\n').replace('\\t', '\t')

    if args.level and caption:
        prefix = tg_utils.LEVEL_PREFIXES[args.level]
        if not caption.lstrip().startswith(prefix):
            caption = f"{prefix} {caption}"

    silent = args.silent or (args.level == "info")

    # ---- Send to each admin --------------------------------------------------
    sent_count = 0
    fail_count = 0

    thread_id = args.thread_id or tg_utils.get_global_thread_id()

    for chat_id in admin_ids:
        ok, err = send_photo(
            token, chat_id, args.photo, caption=caption, 
            silent=silent, thread_id=thread_id, parse_mode=args.parse_mode
        )
        if ok:
            print(f"✓ Photo sent to {chat_id}")
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
