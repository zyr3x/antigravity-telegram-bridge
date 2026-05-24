#!/usr/bin/env python3
"""
Telegram Message Editor for Antigravity agents.

Edits an existing text message via the Bot API.
Designed for updating progress bars or status messages.

Usage:
    python3 tg_edit_message.py --message-id 12345 --chat-id 987654 --text "New text"
    python3 tg_edit_message.py --message-id 12345 --chat-id 987654 --text "New text" --buttons "Cancel:cb_cancel"
"""

import os
import sys
import argparse
import tg_utils

def edit_message(token, chat_id, message_id, text, buttons=None, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if parse_mode and parse_mode.lower() != "none":
        payload["parse_mode"] = parse_mode
    
    if buttons:
        inline_keyboard = []
        for btn_group in buttons.split(";"):
            row = []
            for btn in btn_group.split(","):
                if ":" in btn:
                    text_btn, cb_data = btn.split(":", 1)
                    row.append({"text": text_btn.strip(), "callback_data": cb_data.strip()})
            if row:
                inline_keyboard.append(row)
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}

    return tg_utils.post_json(url, payload)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Edit an existing Telegram text message.",
    )
    parser.add_argument(
        "--message-id", "-i",
        required=True,
        type=int,
        help="ID of the message to edit."
    )
    parser.add_argument(
        "--chat-id", "-c",
        required=True,
        help="ID of the chat."
    )
    parser.add_argument(
        "--text", "-t",
        required=True,
        help="New message text."
    )
    parser.add_argument(
        "--level", "-l",
        choices=["info", "warning", "critical"],
        default=None,
        help="Prepend level emoji."
    )
    parser.add_argument(
        "--buttons", "-b",
        default=None,
        help="Inline buttons format: 'Text:cb_data,Text2:cb_data2;Row2Text:cb_data3'."
    )
    parser.add_argument(
        "--parse-mode",
        default="HTML",
        help="Parse mode (HTML, MarkdownV2, None). Default: HTML."
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Explicit path to .env file."
    )
    args = parser.parse_args()

    tg_utils.load_dotenv(args.env_file)
    token = tg_utils.get_token()

    if not token:
        print("SKIP: Telegram not configured. Message not edited.")
        sys.exit(0)

    text = args.text.replace('\\n', '\n').replace('\\t', '\t')

    if args.level:
        prefix = tg_utils.LEVEL_PREFIXES[args.level]
        if not text.lstrip().startswith(prefix):
            text = f"{prefix} {text}"

    ok, err = edit_message(token, args.chat_id, args.message_id, text, buttons=args.buttons, parse_mode=args.parse_mode)
    if ok:
        print(f"✓ Message {args.message_id} edited in chat {args.chat_id}")
        sys.exit(0)
    else:
        print(f"✗ Failed to edit message {args.message_id}: {err}")
        sys.exit(2)

if __name__ == "__main__":
    main()
