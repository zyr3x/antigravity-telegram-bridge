#!/usr/bin/env python3
"""
Telegram Document Sender for Antigravity agents.

Sends a local file as a document to all Telegram admin users.
Zero-dependency multipart/form-data implementation.

Usage:
    python3 tg_send_document.py --document /path/to/file.pdf --caption "Report"
    python3 tg_send_document.py --document /tmp/logs.txt --thread-id 123
"""

import os
import sys
import json
import time
import uuid
import mimetypes
import argparse
import urllib.request
import urllib.error
import urllib.parse
import tg_utils

# ---------------------------------------------------------------------------
# Multipart Form Builder
# ---------------------------------------------------------------------------

def _build_multipart_payload(fields, file_field, file_path):
    boundary = uuid.uuid4().hex
    parts = []
    
    for key, val in fields:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{val}\r\n".encode("utf-8"))
    
    filename = os.path.basename(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
        
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    
    with open(file_path, "rb") as f:
        file_content = f.read()
    parts.append(file_content)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    
    return b"".join(parts), boundary

def send_document(token, chat_id, filepath, caption=None, silent=False, thread_id=None, parse_mode="HTML"):
    """Send a document via sendDocument with multipart upload."""
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    
    fields = [("chat_id", str(chat_id))]
    if caption:
        fields.append(("caption", caption))
    if parse_mode and parse_mode.lower() != "none":
        fields.append(("parse_mode", parse_mode))
    if thread_id:
        fields.append(("message_thread_id", str(thread_id)))
    if silent:
        fields.append(("disable_notification", "true"))

    body, boundary = _build_multipart_payload(fields, "document", filepath)

    last_error = None
    for attempt in range(tg_utils.MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST"
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
    parser = argparse.ArgumentParser(description="Send a local file as a document via Telegram.")
    parser.add_argument("--document", "-d", required=True, help="Path to the file to send.")
    parser.add_argument("--caption", "-c", default=None, help="Optional text caption (supports HTML).")
    parser.add_argument("--thread-id", "-t", default=None, help="Specific thread ID.")
    parser.add_argument("--silent", "-s", action="store_true", help="Send silently.")
    parser.add_argument("--env-file", default=None, help="Explicit path to .env file.")
    parser.add_argument("--parse-mode", default="HTML", help="Parse mode (HTML, MarkdownV2, None). Default: HTML.")
    args = parser.parse_args()

    tg_utils.load_dotenv(args.env_file)
    token = tg_utils.get_token()
    admin_ids = tg_utils.get_admin_ids()

    if not token or not admin_ids:
        print("SKIP: Telegram not configured. Document not sent.")
        sys.exit(0)

    if not os.path.isfile(args.document):
        print(f"Error: File '{args.document}' not found.")
        sys.exit(2)

    thread_id = args.thread_id or tg_utils.get_global_thread_id()

    sent_count = 0
    fail_count = 0

    for chat_id in admin_ids:
        ok, err = send_document(
            token, chat_id, args.document, caption=args.caption, 
            silent=args.silent, thread_id=thread_id, parse_mode=args.parse_mode
        )
        if ok:
            print(f"✓ Sent to {chat_id}")
            sent_count += 1
        else:
            print(f"✗ Failed for {chat_id}: {err}")
            fail_count += 1

    if fail_count == 0:
        sys.exit(0)
    elif sent_count > 0:
        sys.exit(1)
    else:
        sys.exit(2)

if __name__ == "__main__":
    main()
