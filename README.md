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
- `!chat_enable [room_id]`: Enable autonomous chat in a room (current room if no ID provided)
- `!chat_disable [room_id]`: Disable autonomous chat in a room (current room if no ID provided)
- `!chat_status`: Show autonomous chat status for all rooms

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
!chat_settings quirk 10                 # Set quirk chance percentage (0-100)
```

All settings are automatically saved and persist across bot restarts.

### Per-Room Chat Controls

The owner can enable or disable autonomous chat on a per-room basis with persistent settings:

```
!chat_enable                            # Enable autonomous chat in current room
!chat_enable !room:example.com          # Enable autonomous chat in specific room
!chat_disable                           # Disable autonomous chat in current room  
!chat_disable !room:example.com         # Disable autonomous chat in specific room
!chat_reset                             # Reset current room to default settings
!chat_reset !room:example.com           # Reset specific room to default settings
!list_rooms                             # Show all rooms with their chat status
```

**Persistent Settings**: All room chat preferences are automatically saved to `store/autonomous_chat_settings.json` and persist across bot restarts. This means:

- Once you enable/disable chat in a room, that setting is remembered permanently
- The bot will maintain these preferences even after restarting
- Settings are saved immediately when you use `!chat_enable` or `!chat_disable`

**Default Behavior**: Autonomous chat is enabled by default in all rooms. Only rooms where you've explicitly used `!chat_enable` or `!chat_disable` have stored preferences.

**Use Cases**:
- Disable in busy public rooms where the bot might be disruptive
- Enable only in specific project or discussion rooms
- Temporarily disable during meetings or focused work sessions
- Reset rooms back to default behavior with `!chat_reset`

**Settings Management**: The `!chat_settings` command also saves all configuration changes (response intervals, history length, etc.) persistently.

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
6. **Configure the bot** (see Configuration section below)

## Configuration

⚠️ **Important**: Never commit secrets to git! All secret values should be stored in environment variables.

### Environment Variables Setup

1. **Copy the environment template:**
   ```bash
   cp env.example .env
   ```

2. **Edit `.env` with your actual credentials:**
   ```bash
   # Matrix bot configuration
   HOMESERVER=https://matrix.themultiverse.school
   USER_ID=@your-bot:themultiverse.school
   ACCESS_TOKEN=your-matrix-access-token
   
   # External API configuration
   API_URL=https://your-api-endpoint.com/api/posts
   API_TOKEN=your-api-token-here
   
   # OpenAI API configuration
   OPENAI_API_KEY=your-openai-api-key-here
   
   # Bot configuration
   OWNER_ID=@your-username:themultiverse.school
   DEVICE_ID=your-device-id
   ```

3. **The `.env` file is automatically ignored by git** (see `.gitignore`)

### Configuration Files

The bot uses a clean separation of concerns:

- **`.env`**: Contains all secret values (tokens, API keys, etc.)
- **`bot_config.py`**: Loads environment variables and provides configuration
- **`clients.py`**: Initializes external service clients
- **`config.example.py`**: Shows the configuration structure (no secrets)

### Security Notes
- Never commit `.env` or any file with secrets to version control
- Use environment variables for production deployments
- Rotate credentials if they're accidentally exposed
- Use a dedicated bot account with minimal permissions
- The `.env` file is excluded from git automatically

### Production Deployment

For production, you can set environment variables directly instead of using a `.env` file:

```bash
export HOMESERVER="https://matrix.themultiverse.school"
export USER_ID="@your-bot:themultiverse.school" 
export ACCESS_TOKEN="your-matrix-access-token"
export API_URL="https://your-api-endpoint.com/api/posts"
export API_TOKEN="your-api-token-here"
export OPENAI_API_KEY="your-openai-api-key-here"
export OWNER_ID="@your-username:themultiverse.school"
export DEVICE_ID="your-device-id"

uv run python main.py
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
├── bot_config.py        # Configuration loader (loads from .env)
├── clients.py           # External service clients initialization
├── actions.py           # URL processing and API actions
├── crawling.py          # Web crawling functionality
├── post_client.py       # API client for posting content
├── baml_src/           # BAML AI function definitions
│   ├── chat.baml       # Conversation AI functions
│   ├── article.baml    # Article parsing functions
│   └── post.baml       # Social media post generation
├── .env                # Environment variables (not in repo)
├── env.example         # Environment variables template
├── config.example.py   # Configuration structure example
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

## ArXiv Auto-Posting

The bot can automatically discover and post trending AI papers from arXiv to designated channels.

### Trending Paper Filtering

The system uses sophisticated filtering to ensure only truly trending papers are posted:

**🏆 Tier 1 - High Impact:** Papers with Altmetric score ≥ 5.0
**📱 Tier 2 - Social Engagement:** Papers with Altmetric ≥ 2.0 AND social activity (3+ tweets, 1+ Reddit, or news coverage)  
**⚡ Tier 3 - Hot & Recent:** Very recent papers (<12h) in hot AI categories with priority score ≥ 80
**🌟 Tier 4 - Emerging:** Papers <24h old with any Altmetric attention

### Commands

```
!trending_ai [days] [count]             # Show trending papers with Altmetric data
!arxiv_status                           # Show auto-poster status and queue info
!arxiv_discover                         # Manually discover trending papers  
!arxiv_post                             # Manually post next paper from queue
!arxiv_queue [count]                    # Show papers in posting queue
!arxiv_config [setting] [value]         # Configure auto-poster settings
!arxiv_trending [days]                  # Analyze Altmetric statistics
!arxiv_criteria                         # Show trending filtering criteria
```

**Target Channel**: Papers are posted to `#ai-papers:themultiverse.school`

**Automatic Operation**: The bot runs maintenance cycles every 6 hours to discover new papers and posts up to 5 papers per day with 4-hour intervals between posts.
