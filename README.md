# 🔗 Antigravity Telegram Bridge

Universal Telegram chat interface for [Antigravity](https://github.com/google-deepmind/antigravity) agents.

Drop this plugin into any project and instantly get a **two-way Telegram chat** to control your AI agent — send commands, receive notifications, get status updates.

---

## ⚡ Quick Start (3 steps)

### 1. Create a Telegram Bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (e.g. `7123456789:AAH...`)
4. Get your **Telegram user ID** — send `/start` to [@userinfobot](https://t.me/userinfobot)

### 2. Install the Plugin

**Option A — Global Plugin (all projects):**
```bash
cp -r antigravity-telegram-bridge ~/.gemini/config/plugins/
```

**Option B — Project Skill (single project):**
```bash
cp -r antigravity-telegram-bridge/skills/telegram-bridge your-project/.agents/skills/
```

### 3. Configure

Run the setup wizard:
```bash
python3 ~/.gemini/config/plugins/antigravity-telegram-bridge/skills/telegram-bridge/scripts/tg_setup.py
```

Or manually add to your project's `.env`:
```env
TG_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TG_ADMIN_IDS=123456789
```

> Multiple admins: `TG_ADMIN_IDS=123456789,987654321`

---

## 📦 What's Inside

```
antigravity-telegram-bridge/
├── plugin.json                    # Antigravity plugin metadata
├── README.md                      # This file
└── skills/
    └── telegram-bridge/
        ├── SKILL.md               # Agent instructions (auto-loaded)
        └── scripts/
            ├── tg_inbox.py        # Receive messages (getUpdates + offset)
            ├── tg_send.py         # Send text messages
            ├── tg_send_photo.py   # Send photos with captions
            └── tg_setup.py        # Interactive setup wizard
```

---

## 🛠 Usage

### Send a message
```bash
python3 scripts/tg_send.py -m "Hello from Antigravity!"
python3 scripts/tg_send.py -m "⚠️ Alert!" --level warning
python3 scripts/tg_send.py -m "🔴 Critical issue" --level critical
```

### Send a photo
```bash
python3 scripts/tg_send_photo.py --photo /path/to/image.png --caption "Screenshot"
```

### Check inbox
```bash
python3 scripts/tg_inbox.py              # Fetch new messages (advances offset)
python3 scripts/tg_inbox.py --peek       # Fetch without marking as read
python3 scripts/tg_inbox.py --mark-read  # Skip all pending messages
```

### Message levels

| Level | Emoji | Behavior |
|-------|-------|----------|
| `info` (default) | 🔵 | Silent delivery (no push sound) |
| `warning` | 🟡 | Standard delivery |
| `critical` | 🔴 | Sent with notification sound |

---

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TG_BOT_TOKEN` | ✅ | Telegram Bot API token from BotFather |
| `TG_ADMIN_IDS` | ✅ | Comma-separated Telegram user IDs |

> **Backward compatibility:** Also supports `AGENT_TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_IDS` as fallback names.

---

## 🤖 How the Agent Uses It

When the plugin is installed, Antigravity agents automatically:

1. **Set up a CRON** to check the Telegram inbox every 5 minutes
2. **Process incoming messages** using all available MCP tools
3. **Reply** to each message via Telegram
4. **Send notifications** for important events

The SKILL.md contains all instructions the agent needs — no additional configuration required.

---

## 📋 Requirements

- Python 3.8+
- `requests` library (`pip install requests`)
- Telegram Bot API token

---

## 📄 License

MIT
