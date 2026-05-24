#!/usr/bin/env python3
"""
Telegram Chat Action Sender for Antigravity agents.

Sends a chat action (like 'typing' or 'upload_document') to all Telegram admin users.

Usage:
    python3 tg_send_action.py --action typing
    python3 tg_send_action.py --action upload_document --thread-id 123
"""

import os
import sys
import argparse
import tg_utils


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def send_chat_action(token, chat_id, action, thread_id=None):
    """Send a chat action via sendChatAction."""
    url = f"https://api.telegram.org/bot{token}/sendChatAction"
    payload = {
        "chat_id": chat_id,
        "action": action,
    }
    if thread_id:
        payload["message_thread_id"] = thread_id

    return tg_utils.post_json(url, payload)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Send a Telegram chat action to all admin users.",
    )
    parser.add_argument(
        "--action", "-a",
        required=True,
        choices=["typing", "upload_photo", "record_video", "upload_video", "record_voice", "upload_voice", "upload_document", "choose_sticker", "find_location", "record_video_note", "upload_video_note"],
        help="The chat action to send.",
    )
    parser.add_argument(
        "--thread-id", "-t",
        default=None,
        help="Specific thread (topic) ID to send to. Overrides TG_THREAD_ID from .env",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Explicit path to .env file.",
    )
    args = parser.parse_args()

    tg_utils.load_dotenv(args.env_file)
    token = tg_utils.get_token()
    admin_ids = tg_utils.get_admin_ids()

    if not token or not admin_ids:
        print("SKIP: Telegram not configured. Action not sent.")
        sys.exit(0)

    thread_id = args.thread_id or tg_utils.get_global_thread_id()

    sent_count = 0
    fail_count = 0

    for chat_id in admin_ids:
        ok, err = send_chat_action(token, chat_id, args.action, thread_id)
        if ok:
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
