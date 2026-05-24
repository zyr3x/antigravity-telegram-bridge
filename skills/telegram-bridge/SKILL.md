---
name: telegram-bridge
description: >
  Universal Telegram chat interface for Antigravity agents. Enables two-way
  communication: receive user commands via Telegram and send replies/notifications.
  Activate when the user asks to setup, start, or stop Telegram.
  Works with any project — domain-agnostic.
---

# Telegram Bridge — Agent Instructions

> This skill gives you the ability to communicate with the user through Telegram.
> You can receive commands, answer questions, and send notifications — all via Telegram chat.
> **Do NOT activate automatically.** Only act when the user explicitly requests it.

---

## 1. Resolving Script Paths

Before using any script, you must determine the correct path. Check in this order:

1. **Project skill**: `.agents/skills/telegram-bridge/scripts/`
2. **Global plugin**: `~/.gemini/config/plugins/antigravity-telegram-bridge/skills/telegram-bridge/scripts/`

Test with:
```bash
ls .agents/skills/telegram-bridge/scripts/tg_send.py 2>/dev/null || ls ~/.gemini/config/plugins/antigravity-telegram-bridge/skills/telegram-bridge/scripts/tg_send.py
```

Store the resolved path and reuse it for all commands in the session.

---

## 2. Configuration

The Telegram bridge requires environment variables in the project's `.env` file:

| Variable | Required | Description |
|----------|----------|-------------|
| `TG_BOT_TOKEN` | ✅ | Telegram Bot API token from [@BotFather](https://t.me/BotFather) |
| `TG_ADMIN_IDS` | ✅ | Comma-separated Telegram user IDs (only these users can interact) |
| `TG_THREAD_ID` | ❌ | Topic ID for Forum groups. If set, notifications will route here by default |
| `TG_UPLOADS_DIR` | ❌ | Directory for downloaded files (photos, docs). Default: `<project_root>/.telegram_uploads/` |
| `TG_POLL_INTERVAL` | ❌ | Inbox check frequency in minutes (default: `5`). Examples: `1`, `2`, `5`, `10` |

> **Backward compatibility:** Also accepts `AGENT_TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_IDS`.

> **Availability check:** If no token is set, **skip ALL Telegram operations silently**. Scripts exit with code 0 and empty output. Telegram is never a blocking dependency.

### How `.env` is Resolved

Scripts look for `.env` in this order:
1. Variables already in `os.environ` (highest priority)
2. `--env-file PATH` flag (explicit override)
3. `.env` in the **current working directory** (CWD = project root)
4. Walk upward from CWD until `.env` is found (fallback)

> **Important:** Always run scripts from the **project root** directory.

---

## 3. Commands (On-Demand Only)

> **Critical:** Do NOT create the Telegram CRON automatically. Only act when the user **explicitly requests** it.

### `setup telegram`

**Triggers:** "setup telegram", "настрой телеграм", "configure telegram"

**Action:**
1. Check if `TG_BOT_TOKEN` and `TG_ADMIN_IDS` exist in `.env`
2. **If not configured** — run the setup wizard:
   ```bash
   python3 <scripts_path>/tg_setup.py
   ```
   This interactively asks for the bot token and admin IDs, verifies via API, sends a test message, and saves to `.env`.
3. **If already configured** — reply: "✅ Telegram is already configured. Say 'start telegram' to enable inbox polling."

### `start telegram`

**Triggers:** "start telegram", "enable telegram", "запусти телеграм", "подключи телеграм"

**Action:**
1. Verify Telegram is configured (token + admin IDs in `.env`). If not — prompt to run setup first.
2. Read `TG_POLL_INTERVAL` from `.env` (default: `5`).
3. Create a CRON using the `schedule` tool:

   **Schedule:** `*/<interval> * * * *` (e.g., `*/5 * * * *` for every 5 minutes)

   **Prompt:**
   ```
   Check Telegram inbox for new user messages. Execute:
   1. Run: python3 <scripts_path>/tg_inbox.py
   2. If messages returned (non-empty JSON array):
      - Process each message — interpret the request
      - Use any available MCP tools to fulfill the request
      - Reply via: python3 <scripts_path>/tg_send.py -m "REPLY_TEXT" --level info
   3. If no messages (empty array []): do nothing, end turn.
   Only respond to user messages. Do not start other workflows unless explicitly requested.
   ```

4. Send a confirmation message to Telegram:
   ```bash
   python3 <scripts_path>/tg_send.py -m "🟢 Telegram bridge activated. Checking inbox every <interval> min." --level info
   ```

5. Reply to the user in chat: "✅ Telegram bridge started. Checking inbox every N minutes."

### `stop telegram`

**Triggers:** "stop telegram", "disable telegram", "выключи телеграм", "останови телеграм"

**Action:**
1. Use `manage_task` tool to find and kill the Telegram Inbox CRON task.
2. Send a final message to Telegram:
   ```bash
   python3 <scripts_path>/tg_send.py -m "🔴 Telegram bridge deactivated." --level warning
   ```
3. Reply to the user in chat: "✅ Telegram bridge stopped."

### `status telegram`

**Triggers:** "status telegram", "статус телеграм", "is telegram running?"

**Action:**
1. Check if a Telegram Inbox CRON task is active (use `manage_task` list).
2. Reply with status: running/stopped, poll interval, last check time.

---

## 4. Sending Messages

### Text Messages

```bash
# Info (silent delivery)
python3 <scripts_path>/tg_send.py -m "✅ Task completed" --level info

# Warning
python3 <scripts_path>/tg_send.py -m "⚠️ Something needs attention" --level warning

# Critical (with notification sound)
python3 <scripts_path>/tg_send.py -m "🔴 Critical error" --level critical

# Silent mode
python3 <scripts_path>/tg_send.py -m "Background update" --silent

# With inline buttons (returns message_id which can be edited later)
python3 <scripts_path>/tg_send.py -m "Deploy?" --buttons "Yes:cb_yes,No:cb_no"

# With specific thread ID (Topic)
python3 <scripts_path>/tg_send.py -m "Log entry" --thread-id 123

# Disable HTML parsing (for raw text with < > & symbols)
python3 <scripts_path>/tg_send.py -m "if x < 5: print(x)" --parse-mode None
```

> **Extracting message_id:** `tg_send.py` prints `message_id` in stdout like:
> `✓ Sent to 123456 (message_id: 789)`
> Parse this to use with `tg_edit_message.py`.

### Documents & Files

```bash
python3 <scripts_path>/tg_send_document.py -d /path/to/report.pdf -c "Monthly Report"
python3 <scripts_path>/tg_send_document.py -d /tmp/logs.txt --parse-mode None
```

### Editing Messages

```bash
# Useful for progress bars
python3 <scripts_path>/tg_edit_message.py -i 12345 -c 987654 -t "Processing... 50%"

# With raw text (no HTML parsing)
python3 <scripts_path>/tg_edit_message.py -i 12345 -c 987654 -t "x < 5" --parse-mode None
```

### Chat Actions (Typing status)

```bash
python3 <scripts_path>/tg_send_action.py -a typing
python3 <scripts_path>/tg_send_action.py -a upload_document
```

### Photos

```bash
python3 <scripts_path>/tg_send_photo.py --photo /path/to/image.png --caption "Description"
python3 <scripts_path>/tg_send_photo.py --photo /path/to/chart.png --caption "Chart" --parse-mode None
```

### Message Levels

| Level | Emoji | Behavior |
|-------|-------|----------|
| `info` (default) | 🔵 | Routine updates, sent silently |
| `warning` | 🟡 | Attention needed, standard delivery |
| `critical` | 🔴 | Immediate attention, sent with sound |

### Rules

| Rule | Detail |
|------|--------|
| **NEVER use `$` in message text** | Shell interprets `$` + digits as a variable. Use plain text instead |
| **Newlines** | Use `\\n` in the message string for line breaks |
| **HTML formatting** | Use `<b>bold</b>`, `<i>italic</i>`, `<code>code</code>`. Enabled by default. |
| **Raw text / Code** | **CRITICAL:** If sending code snippets or text with `<`, `>`, `&` symbols, you MUST add `--parse-mode None`. Otherwise Telegram API will crash with `400 Bad Request: can't parse entities` |
| **Message Limits** | Text messages: Max **4096** chars. Captions: Max **1024** chars. If a message is too long, either split it into chunks or save it as a file and send it via `tg_send_document.py` |

---

## 5. Receiving Messages (Inbox)

```bash
# Fetch new messages (advances offset — each message seen only once)
python3 <scripts_path>/tg_inbox.py

# Peek without marking as read
python3 <scripts_path>/tg_inbox.py --peek

# Skip all pending messages
python3 <scripts_path>/tg_inbox.py --mark-read

# Custom uploads directory for file attachments
python3 <scripts_path>/tg_inbox.py --uploads-dir /path/to/uploads
```

### File Downloads

When the user sends a photo, document, voice message, video, or audio file, the inbox automatically downloads it to `<project_root>/.telegram_uploads/`. The JSON output includes `file_path` and `file_type` fields.

Supported file types: `photo`, `document`, `voice`, `audio`, `video`, `video_note`, `sticker`.

### Output Format

JSON array to stdout:
```json
[
  {
    "update_id": 123456,
    "from_id": "123456789",
    "from_name": "User",
    "chat_id": 123456789,
    "date": 1716483600,
    "text": "What is the current status?",
    "type": "message",
    "thread_id": 123
  },
  {
    "update_id": 123457,
    "from_id": "123456789",
    "from_name": "User",
    "chat_id": 123456789,
    "date": 1716483610,
    "text": "Check this screenshot",
    "type": "message",
    "file_path": "/path/to/project/.telegram_uploads/photo_AbCdEf123456.jpg",
    "file_type": "photo"
  },
  {
    "update_id": 123458,
    "from_id": "123456789",
    "from_name": "User",
    "chat_id": 123456789,
    "date": 1716483620,
    "text": "cb_yes",
    "type": "callback_query",
    "callback_id": "9876543210",
    "thread_id": 123
  }
]
```

Empty array `[]` = no new messages.

### Offset Tracking

The `.telegram_offset` file in the project root tracks the last processed message:
- Each message seen **exactly once**
- No duplicates across runs
- `--peek` reads without advancing offset

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

## 7. Troubleshooting

| Problem | Solution |
|---------|----------|
| `SKIP: Telegram not configured` | Run `setup telegram` or add `TG_BOT_TOKEN` + `TG_ADMIN_IDS` to `.env` |
| Messages not received | Check that `TG_ADMIN_IDS` matches your Telegram user ID |
| Bot doesn't respond | Run `status telegram` to check if CRON is active |
| Photos fail to send | Verify the file path is absolute and the file exists |
| `.env` not found | Run scripts from the project root, or use `--env-file` flag |

---

> **Remember:** Telegram is your communication channel with the user. Always reply to messages promptly and clearly. Use appropriate urgency levels for notifications. Never let a message go unanswered.
