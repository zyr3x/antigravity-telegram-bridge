---
name: telegram-bridge
description: >
  Universal Telegram chat interface for Antigravity agents. Enables two-way
  communication: receive user commands via Telegram and send replies/notifications.
  Activate for ANY task involving Telegram messaging, inbox checking, or
  notification sending. Works with any project — domain-agnostic.
---

# Telegram Bridge — Agent Instructions

> This skill gives you the ability to communicate with the user through Telegram.
> You can receive commands, answer questions, and send notifications — all via Telegram chat.

---

## 1. Configuration

The Telegram bridge requires two environment variables in the project's `.env` file:

| Variable | Required | Description |
|----------|----------|-------------|
| `TG_BOT_TOKEN` | ✅ | Telegram Bot API token from [@BotFather](https://t.me/BotFather) |
| `TG_ADMIN_IDS` | ✅ | Comma-separated Telegram user IDs (only these users can interact) |
| `TG_POLL_INTERVAL` | ❌ | Inbox check frequency in minutes (default: `5`). Examples: `1`, `2`, `5`, `10` |

> **Backward compatibility:** The scripts also accept `AGENT_TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_IDS` as fallback variable names.

> **Availability check:** If neither `TG_BOT_TOKEN` nor `AGENT_TELEGRAM_BOT_TOKEN` is set, **skip ALL Telegram operations silently**. The scripts handle this gracefully (exit code 0, empty output). Telegram is never a blocking dependency.

### How `.env` is Resolved

The scripts look for `.env` in this order:
1. Variables already in `os.environ` (highest priority)
2. `--env-file PATH` flag (explicit override)
3. `.env` in the **current working directory** (CWD = project root)
4. Walk upward from CWD until `.env` is found (fallback)

> **Important:** When running scripts, always run from the **project root** so that `.env` is found correctly.

---

## 2. Sending Messages

Use the notifier script to send text messages to all admin users.

### Script Location

```
skills/telegram-bridge/scripts/tg_send.py
```

> **Path note:** When installed as a global plugin, the full path is:
> `~/.gemini/config/plugins/antigravity-telegram-bridge/skills/telegram-bridge/scripts/tg_send.py`
> When installed as a project skill:
> `.agents/skills/telegram-bridge/scripts/tg_send.py`
> Use whichever path matches your installation.

### Usage

```bash
# Standard info notification (sent silently, no push sound)
python3 <path>/scripts/tg_send.py -m "✅ Task completed successfully" --level info

# Warning notification
python3 <path>/scripts/tg_send.py -m "⚠️ Something needs attention" --level warning

# Critical alert (sent with sound)
python3 <path>/scripts/tg_send.py -m "🔴 Critical error occurred" --level critical

# Silent mode (no notification sound regardless of level)
python3 <path>/scripts/tg_send.py -m "Background update" --silent
```

### Urgency Levels

| Level | Emoji | Behavior |
|-------|-------|----------|
| `info` (default) | 🔵 | Routine updates, sent silently (no push notification sound) |
| `warning` | 🟡 | Attention needed, standard delivery |
| `critical` | 🔴 | Immediate attention required, sent with notification sound |

### Rules

| Rule | Detail |
|------|--------|
| **NEVER use `$` in message text** | The shell interprets `$` + digits as a variable. Use plain numbers instead (e.g., `379.30 USDT` not `$379.30`) |
| **Newlines** | Use `\\n` in the message string for line breaks |
| **HTML formatting** | Messages use HTML parse mode. You can use `<b>bold</b>`, `<i>italic</i>`, `<code>code</code>` |

---

## 3. Sending Photos

Use the photo script to send images with captions.

### Script Location

```
skills/telegram-bridge/scripts/tg_send_photo.py
```

### Usage

```bash
# Photo with caption
python3 <path>/scripts/tg_send_photo.py --photo /path/to/image.png --caption "📊 Analysis result"

# Photo with level prefix
python3 <path>/scripts/tg_send_photo.py --photo /path/to/chart.png --caption "Chart analysis" --level info

# Silent photo
python3 <path>/scripts/tg_send_photo.py --photo /path/to/screenshot.png --caption "Update" --silent
```

---

## 4. Receiving Messages (Inbox)

The inbox script fetches unread messages sent by admin users to the bot.

### Script Location

```
skills/telegram-bridge/scripts/tg_inbox.py
```

### Usage

```bash
# Fetch new messages (advances offset — each message seen only once)
python3 <path>/scripts/tg_inbox.py

# Peek without marking as read (re-readable)
python3 <path>/scripts/tg_inbox.py --peek

# Skip all pending messages (advance offset, no output)
python3 <path>/scripts/tg_inbox.py --mark-read
```

### Output Format

JSON array printed to stdout:
```json
[
  {
    "update_id": 123456,
    "from_id": "123456789",
    "from_name": "User",
    "chat_id": 123456789,
    "date": 1716483600,
    "text": "What is the current status?"
  }
]
```

Empty array `[]` means no new messages.

### Offset Tracking

The script maintains a `.telegram_offset` file in the project root to track the last processed message. This ensures:
- Each message is seen **exactly once**
- No duplicates across multiple runs
- `--peek` mode reads without advancing the offset

---

## 5. CRON Setup (Mandatory)

At the start of the **FIRST session** (or whenever the CRON is not running), you **MUST** create a Telegram Inbox CRON using the `schedule` tool.

### Telegram Inbox CRON

**Schedule:** Read `TG_POLL_INTERVAL` from `.env` to determine the frequency. Build the cron expression as `*/<interval> * * * *`.

| `TG_POLL_INTERVAL` | CRON Expression | Checks per hour |
|--------------------|-----------------|------------------|
| `1` | `*/1 * * * *` | 60 (real-time) |
| `2` | `*/2 * * * *` | 30 |
| `5` (default) | `*/5 * * * *` | 12 |
| `10` | `*/10 * * * *` | 6 |
| `15` | `*/15 * * * *` | 4 |
| `30` | `*/30 * * * *` | 2 |

> **How to read `TG_POLL_INTERVAL`:** Run `python3 -c "import os; [exec(f'os.environ.setdefault(*l.strip().split(\"=\",1))') for l in open('.env') if '=' in l and not l.startswith('#')]; print(os.environ.get('TG_POLL_INTERVAL','5'))"` — this prints the configured interval or `5` if not set.

**Prompt for `schedule` tool:**
```
Check Telegram inbox for new user messages. Execute:
1. Run: python3 <SKILL_SCRIPTS_PATH>/tg_inbox.py
2. If messages returned (non-empty JSON array):
   - Process each message — interpret the request
   - Use any available MCP tools to fulfill the request
   - Reply via: python3 <SKILL_SCRIPTS_PATH>/tg_send.py -m "REPLY_TEXT" --level info
3. If no messages (empty array []): do nothing, end turn.
Only respond to user messages. Do not start other workflows unless explicitly requested.
```

> **Important:** Replace `<SKILL_SCRIPTS_PATH>` with the actual path to the scripts directory based on your installation (global plugin or project skill).

### Verification

At session start, verify the Telegram Inbox CRON is running. If missing — create it using the `schedule` tool BEFORE proceeding with any other work.

---

## 6. Message Processing Rules

| Rule | Detail |
|------|--------|
| **Priority** | User messages are processed BEFORE any other scheduled work |
| **No duplicates** | Offset tracking ensures each message is seen exactly once |
| **Full capabilities** | Use ANY available MCP tool to answer the user's request |
| **Always reply** | Every processed message gets a Telegram response |
| **Security** | Messages from non-admin users are silently ignored |
| **No blocking** | If Telegram is not configured, skip silently — never block the main workflow |

---

## 7. Quick Reference

```bash
# ---- Send text message ----
python3 <path>/scripts/tg_send.py -m "MESSAGE" [--level info|warning|critical] [--silent]

# ---- Send photo ----
python3 <path>/scripts/tg_send_photo.py --photo FILE --caption "TEXT" [--level info|warning|critical] [--silent]

# ---- Check inbox ----
python3 <path>/scripts/tg_inbox.py            # fetch + advance offset
python3 <path>/scripts/tg_inbox.py --peek      # fetch without advancing
python3 <path>/scripts/tg_inbox.py --mark-read # skip all pending

# ---- Setup ----
python3 <path>/scripts/tg_setup.py             # interactive setup wizard
```

---

## 8. Troubleshooting

| Problem | Solution |
|---------|----------|
| `SKIP: Telegram not configured` | Add `TG_BOT_TOKEN` and `TG_ADMIN_IDS` to `.env` in project root |
| Messages not received | Check that `TG_ADMIN_IDS` matches your Telegram user ID |
| Bot doesn't respond | Ensure the CRON is running (`schedule` tool). Check `.telegram_offset` file |
| Photos fail to send | Verify the file path is absolute and the file exists |
| `.env` not found | Run scripts from the project root directory, or use `--env-file` flag |

---

> **Remember:** Telegram is your communication channel with the user. Always reply to messages promptly and clearly. Use appropriate urgency levels for notifications. Never let a message go unanswered.
