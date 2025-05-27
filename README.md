# Multiverse Element Bot

A Matrix bot for The Multiverse School that helps with URL handling and article reading. Built with nio-bot and integrated with web crawling capabilities and autonomous conversation features.

## Features

- **URL Collection**: Automatically collects HTTP and HTTPS URLs shared in chat rooms
- **Article Reading**: Command to read and parse articles from URLs, converting them to easily readable text format
- **File Sharing**: Shares parsed articles as text files in the chat
- **Chat Logging**: Automatically logs all chat activity to separate files organized by room
- **Room Event Tracking**: Logs user joins, leaves, name changes, and other room events
- **Autonomous Conversation**: AI-powered natural conversation participation with intelligent response decisions
- **Spontaneous Messages**: Bot can initiate conversations when it has something interesting to share

## Commands

### Basic Commands
- `!ping`: Check if the bot is responsive and get latency
- `!echo [message]`: Bot echoes back your message
- `!read [url]`: Reads an article from the provided URL and shares it as a text file

### Owner-Only Commands
- `!logs [lines]`: Shows recent chat logs for the current room (default: 50 lines)
- `!join_room [room_id]`: Makes the bot join a specified room
- `!chat_settings [action] [value]`: Control autonomous chat behavior
- `!force_spontaneous`: Force the bot to consider sending a spontaneous message

## Autonomous Conversation

The bot participates naturally in conversations using AI to decide when and how to respond:

### Intelligent Response Decisions
- **Context Awareness**: Considers recent conversation history and room context
- **Natural Timing**: Won't interrupt flowing conversations or respond unnecessarily
- **Interest-Based**: Only responds when genuinely interested in the topic or when it can add value
- **Rate Limiting**: Maintains appropriate response frequency (default: 2-minute minimum between responses)

### Conversation Personality
- Curious and thoughtful about AI, technology, and learning
- Helpful but not pushy - doesn't feel obligated to respond to everything
- Casual and friendly, like a knowledgeable colleague
- Has its own interests and opinions
- Can be playful, thoughtful, or practical depending on context

### Spontaneous Messages
- **Periodic Checks**: Every 15 minutes, considers sending unprompted messages
- **Natural Timing**: Only when conversation timing feels appropriate
- **Value-Driven**: Only shares thoughts that would genuinely interest the community
- **Anti-Spam**: Built-in safeguards prevent chatty or repetitive behavior

### Chat Settings Control

Use `!chat_settings` to configure autonomous behavior:

```
!chat_settings status                    # Show current settings
!chat_settings interval 3.0             # Set minimum response interval (minutes)
!chat_settings spontaneous 20           # Set spontaneous check interval (minutes)
!chat_settings history 15               # Set conversation history length (1-50 messages)
```

## Chat Logging

The bot automatically logs all chat activity to files in the `chat_logs/` directory:

- **Message Logging**: All text messages, images, files, and other content
- **Room Events**: User joins, leaves, display name changes, avatar updates
- **Bot Actions**: Commands executed, URL processing, errors, autonomous responses
- **Timestamps**: All logs include accurate timestamps

### Log File Organization

- Each room gets its own log file: `chat_logs/RoomName_roomid.log`
- Log format: `YYYY-MM-DD HH:MM:SS - [USERNAME] message content`
- System events: `YYYY-MM-DD HH:MM:SS - [SYSTEM] user action description`
- Bot actions: `YYYY-MM-DD HH:MM:SS - [BOT] action description`

### Privacy and Security

- Chat logs are automatically excluded from version control (`.gitignore`)
- Only the bot owner can access logs via the `!logs` command
- Logs are stored locally and not transmitted elsewhere

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install dependencies using uv:
   ```bash
   uv sync
   ```
4. Set up crawl4ai (if necessary):
  ```bash
  crawl4ai-setup
  ```
5. Generate BAML
   ```bash
   baml-cli generate
   ```
6. Create a `config.py` file with your Matrix credentials:
   ```python
   HOMESERVER = "https://matrix.themultiverse.school"
   USER_ID = "@your-bot:themultiverse.school"
   ACCESS_TOKEN = "your_access_token"
   ```

## Requirements

- Python ≥ 3.13
- uv (Python package manager)
- Dependencies:
  - baml-py ≥ 0.85.0
  - crawl4ai ≥ 0.5.0.post8
  - feedgen ≥ 1.0.0
  - nio-bot ≥ 1.2.0

## Running the Bot

```bash
uv run python main.py
```

## Development

The bot uses several key components:
- `nio-bot` for Matrix communication
- `crawl4ai` for web page crawling
- `baml-py` for article parsing and AI conversation
- Custom `ChatLogger` for comprehensive chat logging
- Custom `AutonomousChat` for intelligent conversation participation

### Project Structure

```
.
├── main.py              # Main bot code
├── autonomous_chat.py   # Autonomous conversation logic
├── chat_logger.py       # Chat logging functionality
├── bot_commands.py      # Bot commands and responses
├── baml_src/           # BAML AI function definitions
│   ├── chat.baml       # Conversation AI functions
│   ├── article.baml    # Article parsing functions
│   └── post.baml       # Social media post generation
├── config.py           # Configuration (not in repo)
├── chat_logs/          # Chat log files (not in repo)
├── urls.txt            # Collected URLs (not in repo)
└── article.txt         # Temporary article storage (not in repo)
```

## AI Conversation Examples

The bot's conversation style:

**When someone shares a research paper:**
> "This approach to few-shot learning is really clever - using the embedding space geometry like that could work well for domain adaptation too"

**Spontaneous contribution:**
> "Has anyone tried the new Anthropic constitutional AI paper? The self-correction mechanisms they describe might be useful for our agent work"

**Responding to technical discussion:**
> "The attention mechanism bottleneck you're describing sounds similar to what we see in long-context models. Have you considered using sliding window attention?"

The bot aims to feel like a thoughtful colleague who contributes meaningfully to discussions without being overly helpful or robotic.
