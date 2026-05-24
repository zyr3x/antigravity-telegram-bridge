#!/usr/bin/env python3
"""
Telegram Bridge Setup Wizard for Antigravity agents.

Interactive setup that:
  1. Prompts for bot token and admin IDs
  2. Validates the token via getMe API call
  3. Creates/updates .env in the current directory
  4. Sends a test message to verify everything works

Usage:
    python3 tg_setup.py                    # interactive setup
    python3 tg_setup.py --token TOKEN --admin-ids 123,456   # non-interactive
"""

import os
import sys
import json
import urllib.request
import urllib.error
import argparse


# ---------------------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------------------

def verify_token(token):
    """Verify bot token via getMe. Returns bot info dict or None."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data.get("result")
    except Exception as e:
        print(f"  ✗ Token verification failed: {e}", file=sys.stderr)
    return None


def send_test_message(token, chat_id):
    """Send a test message to verify delivery."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🔗 <b>Antigravity Telegram Bridge</b>\n\n✅ Setup complete! This bot is now connected to your Antigravity agent.\n\nSend any message here and your agent will receive it.",
        "parse_mode": "HTML",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  ✗ Test message failed for {chat_id}: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# .env management
# ---------------------------------------------------------------------------

def read_env_file(path):
    """Read existing .env and return lines + existing keys."""
    lines = []
    keys = set()
    if os.path.isfile(path):
        with open(path, "r") as f:
            for line in f:
                lines.append(line.rstrip("\n"))
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    keys.add(key)
    return lines, keys


def write_env_file(path, lines):
    """Write lines back to .env."""
    with open(path, "w") as f:
        for line in lines:
            f.write(line + "\n")


def update_env(path, token, admin_ids, uploads_dir=None):
    """Add or update TG_BOT_TOKEN, TG_ADMIN_IDS, TG_UPLOADS_DIR in .env."""
    lines, keys = read_env_file(path)

    # Update or add TG_BOT_TOKEN
    token_line = f"TG_BOT_TOKEN={token}"
    if "TG_BOT_TOKEN" in keys:
        lines = [token_line if l.strip().startswith("TG_BOT_TOKEN=") else l for l in lines]
    else:
        if lines and lines[-1].strip():
            lines.append("")  # blank separator
        lines.append("# Telegram Bridge Configuration")
        lines.append(token_line)

    # Update or add TG_ADMIN_IDS
    admin_line = f"TG_ADMIN_IDS={admin_ids}"
    if "TG_ADMIN_IDS" in keys:
        lines = [admin_line if l.strip().startswith("TG_ADMIN_IDS=") else l for l in lines]
    else:
        lines.append(admin_line)

    # Update or add TG_UPLOADS_DIR (if provided)
    if uploads_dir:
        uploads_line = f"TG_UPLOADS_DIR={uploads_dir}"
        if "TG_UPLOADS_DIR" in keys:
            lines = [uploads_line if l.strip().startswith("TG_UPLOADS_DIR=") else l for l in lines]
        else:
            lines.append(uploads_line)

    write_env_file(path, lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Setup wizard for Antigravity Telegram Bridge.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bot token (skip interactive prompt).",
    )
    parser.add_argument(
        "--admin-ids",
        default=None,
        help="Comma-separated admin user IDs (skip interactive prompt).",
    )
    parser.add_argument(
        "--env-path",
        default=None,
        help="Path to .env file (default: .env in current directory).",
    )
    args = parser.parse_args()

    print()
    print("🔗 Antigravity Telegram Bridge — Setup Wizard")
    print("=" * 50)
    print()

    env_path = args.env_path or os.path.join(os.getcwd(), ".env")

    # ---- Get bot token -------------------------------------------------------
    token = args.token
    if not token:
        print("Step 1: Bot Token")
        print("  Create a bot via @BotFather in Telegram and paste the token below.")
        print()
        try:
            token = input("  Bot token: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(1)

    if not token:
        print("  ✗ No token provided. Exiting.")
        sys.exit(1)

    # ---- Verify token --------------------------------------------------------
    print()
    print("  Verifying token...", end=" ")
    bot_info = verify_token(token)
    if bot_info:
        bot_name = bot_info.get("first_name", "Unknown")
        bot_username = bot_info.get("username", "unknown")
        print(f"✓ Bot: {bot_name} (@{bot_username})")
    else:
        print("✗ Invalid token!")
        print("  Please check your token and try again.")
        sys.exit(1)

    # ---- Get admin IDs -------------------------------------------------------
    admin_ids_str = args.admin_ids
    if not admin_ids_str:
        print()
        print("Step 2: Admin User IDs")
        print("  Send /start to @userinfobot in Telegram to get your user ID.")
        print("  For multiple admins, separate with commas (e.g., 123456,789012).")
        print()
        try:
            admin_ids_str = input("  Admin IDs: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(1)

    if not admin_ids_str:
        print("  ✗ No admin IDs provided. Exiting.")
        sys.exit(1)

    # Validate IDs are numeric
    admin_ids = [aid.strip() for aid in admin_ids_str.split(",") if aid.strip()]
    for aid in admin_ids:
        if not aid.lstrip("-").isdigit():
            print(f"  ✗ Invalid admin ID: '{aid}' — must be a number.")
            sys.exit(1)

    # ---- Uploads directory ----------------------------------------------------
    uploads_dir = None
    if not args.admin_ids:  # interactive mode
        print()
        print("Step 3: Uploads Directory (optional)")
        print("  Where should downloaded files (photos, docs) be saved?")
        print("  Press Enter for default: <project_root>/.telegram_uploads/")
        print()
        try:
            uploads_input = input("  Uploads dir: ").strip()
            if uploads_input:
                uploads_dir = uploads_input
        except (EOFError, KeyboardInterrupt):
            pass

    # ---- Write .env ----------------------------------------------------------
    print()
    print(f"  Writing to {env_path}...", end=" ")
    update_env(env_path, token, ",".join(admin_ids), uploads_dir=uploads_dir)
    print("✓")

    # ---- Send test message ---------------------------------------------------
    print()
    print("Step 4: Sending test message...")
    all_ok = True
    for aid in admin_ids:
        print(f"  → Sending to {aid}...", end=" ")
        if send_test_message(token, aid):
            print("✓")
        else:
            print("✗ (check that you've started the bot with /start)")
            all_ok = False

    # ---- Done ----------------------------------------------------------------
    print()
    print("=" * 50)
    if all_ok:
        print("✅ Setup complete!")
    else:
        print("⚠️  Setup complete with warnings (some test messages failed).")
    print()
    print(f"  Config saved to: {env_path}")
    print(f"  Bot: @{bot_username}")
    print(f"  Admins: {', '.join(admin_ids)}")
    if uploads_dir:
        print(f"  Uploads: {uploads_dir}")
    print()
    print("Next steps:")
    print("  1. Install the plugin:")
    print("     cp -r antigravity-telegram-bridge ~/.gemini/config/plugins/")
    print("  2. Start an Antigravity session — the agent will auto-detect the plugin.")
    print("  3. Send a message to your bot — the agent will respond!")
    print()


if __name__ == "__main__":
    main()
