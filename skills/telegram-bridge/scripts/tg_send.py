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
import argparse
import tg_utils





# ---------------------------------------------------------------------------
# Telegram helpers (stdlib only — zero dependencies)
# ---------------------------------------------------------------------------

def send_message(token, chat_id, text, silent=False, thread_id=None, buttons=None, parse_mode="HTML"):
    """Send a text message via sendMessage."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode and parse_mode.lower() != "none":
        payload["parse_mode"] = parse_mode

    if silent:
        payload["disable_notification"] = True
    if thread_id:
        payload["message_thread_id"] = thread_id
        
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
    parser.add_argument(
        "--thread-id", "-t",
        default=None,
        help="Specific thread ID.",
    )
    parser.add_argument(
        "--buttons", "-b",
        default=None,
        help="Inline buttons. Format: 'Text:cb_data,Text2:cb_data2;Row2Text:cb_data3'.",
    )
    parser.add_argument(
        "--parse-mode",
        default="HTML",
        help="Parse mode (HTML, MarkdownV2, None). Default: HTML."
    )
    args = parser.parse_args()

    # ---- Load configuration --------------------------------------------------
    tg_utils.load_dotenv(args.env_file)

    token = tg_utils.get_token()
    admin_ids = tg_utils.get_admin_ids()

    if not token or not admin_ids:
        print("SKIP: Telegram not configured (TG_BOT_TOKEN or TG_ADMIN_IDS missing). Message not sent.")
        sys.exit(0)

    # ---- Build message text --------------------------------------------------
    text = args.message

    # Convert literal escape sequences from shell
    text = text.replace('\\n', '\n').replace('\\t', '\t')

    if args.level:
        prefix = tg_utils.LEVEL_PREFIXES[args.level]
        if not text.lstrip().startswith(prefix):
            text = f"{prefix} {text}"

    # Auto-silent for info level
    silent = args.silent or (args.level == "info")

    # ---- Send to each admin --------------------------------------------------
    sent_count = 0
    fail_count = 0
    
    thread_id = args.thread_id or tg_utils.get_global_thread_id()

    for chat_id in admin_ids:
        ok, result = send_message(
            token, chat_id, text, silent=silent, 
            thread_id=thread_id, buttons=args.buttons, parse_mode=args.parse_mode
        )
        if ok:
            msg_id = result.get("result", {}).get("message_id", "unknown")
            print(f"✓ Sent to {chat_id} (message_id: {msg_id})")
            sent_count += 1
        else:
            print(f"✗ Failed for {chat_id}: {result}")
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
