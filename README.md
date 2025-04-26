# Multiverse Element Bot

A Matrix bot for The Multiverse School that helps with URL handling and article reading. Built with nio-bot and integrated with web crawling capabilities.

## Features

- **URL Collection**: Automatically collects HTTP and HTTPS URLs shared in chat rooms
- **Article Reading**: Command to read and parse articles from URLs, converting them to easily readable text format
- **File Sharing**: Shares parsed articles as text files in the chat

## Commands

- `!ping`: Check if the bot is responsive and get latency
- `!echo [message]`: Bot echoes back your message
- `!read [url]`: Reads an article from the provided URL and shares it as a text file

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
4. Create a `config.py` file with your Matrix credentials:
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
- `baml-py` for article parsing

### Project Structure

```
.
├── main.py          # Main bot code
├── config.py        # Configuration (not in repo)
├── urls.txt         # Collected URLs (not in repo)
└── article.txt      # Temporary article storage (not in repo)
```