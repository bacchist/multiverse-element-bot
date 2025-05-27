# ArXiv AI Paper Tracker & Auto-Poster

An optional module for the Multiverse Element Bot that tracks trending AI papers from arXiv and can automatically post them to Matrix channels.

## Features

- 🔍 **Smart Search**: Searches across major AI categories (cs.AI, cs.LG, cs.CL, cs.CV, cs.NE, stat.ML)
- 📊 **Popularity Ranking**: Uses Altmetric scores to rank papers by social media mentions and citations
- 🤖 **Auto-Posting**: Automatically discovers and posts trending papers to Matrix channels
- 💬 **AI Comments**: Generates thoughtful comments about papers using BAML
- ⚙️ **Configurable**: Adjustable posting frequency, channels, and discovery settings
- 🛡️ **Safe Integration**: Completely optional - won't break core bot functionality if disabled

## Installation

1. **Install Dependencies**:
   ```bash
   pip install aiohttp
   ```

2. **The modules are already included** in your bot directory:
   - `arxiv_tracker.py` - Core paper tracking functionality
   - `arxiv_auto_poster.py` - Automatic posting system
   - Bot commands are integrated into `bot_commands.py`

3. **Test the Installation**:
   ```bash
   python test_arxiv.py
   ```

## Usage

### Manual Commands (Owner Only)

#### `!trending_ai [days] [count]`
Fetch and display trending AI papers manually.

```
!trending_ai                    # Top 5 papers from last 3 days
!trending_ai 7 10              # Top 10 papers from last 7 days
```

#### `!arxiv_status`
Show the current status of the auto-poster.

#### `!arxiv_discover [days]`
Manually trigger paper discovery.

```
!arxiv_discover                # Discover papers from last 3 days
!arxiv_discover 7              # Discover papers from last 7 days
```

#### `!arxiv_post`
Manually post the next paper from the queue.

#### `!arxiv_queue [count]`
Show papers currently in the posting queue.

```
!arxiv_queue                   # Show top 5 papers in queue
!arxiv_queue 10                # Show top 10 papers in queue
```

#### `!arxiv_config [setting] [value]`
Configure auto-poster settings.

```
!arxiv_config                                    # Show current settings
!arxiv_config channel #ai-papers:server.com     # Change target channel
!arxiv_config max_posts 5                       # Set max posts per day
!arxiv_config interval 4                        # Set posting interval (hours)
```

### Standalone CLI Usage

The tracker can also be used as a standalone command-line tool:

```bash
# Basic usage
python arxiv_tracker.py --days 3 --count 5

# With Altmetric data (slower)
python arxiv_tracker.py --days 2 --count 3

# Skip Altmetric for faster results
python arxiv_tracker.py --days 7 --count 10 --no-altmetric

# JSON output
python arxiv_tracker.py --days 1 --count 5 --format json

# Save to file
python arxiv_tracker.py --days 3 --output papers.json

# Help
python arxiv_tracker.py --help
```

## Configuration

### Auto-Poster Settings

The auto-poster can be configured in `main.py`:

```python
arxiv_auto_poster = ArxivAutoPoster(
    bot=bot,
    target_channel="#ai-papers:themultiverse.school",  # Channel to post to
    max_posts_per_day=3,                               # Max papers per day
    posting_interval=timedelta(hours=6),               # Min time between posts
    discovery_interval=timedelta(hours=8)              # How often to discover new papers
)
```

### Paper Ranking

Papers are ranked by a priority score that considers:

- **Altmetric Score** (×10 weight): Social media mentions, citations, news coverage
- **Recency Bonus**: Papers from the last 24 hours get extra points
- **Category Bonus**: Popular AI categories (cs.AI, cs.LG, etc.) get bonus points

### Target Channel

Change the target channel by editing `main.py` or using the `!arxiv_config` command:

```
!arxiv_config channel #your-channel:your-server.com
```

## How It Works

### Discovery Process

1. **Scheduled Discovery**: Every 8 hours (configurable), the system searches arXiv for new papers
2. **Category Filtering**: Searches across major AI/ML categories
3. **Altmetric Enrichment**: Fetches popularity data for each paper
4. **Priority Scoring**: Calculates a priority score based on multiple factors
5. **Queue Management**: Adds new papers to the posting queue, sorted by priority

### Posting Process

1. **Scheduled Posting**: Every 6 hours (configurable), checks if a paper should be posted
2. **Rate Limiting**: Respects daily posting limits and minimum intervals
3. **Comment Generation**: Uses BAML to generate thoughtful comments about papers
4. **Formatting**: Creates well-formatted Matrix messages with paper details
5. **State Persistence**: Tracks posted papers to avoid duplicates

### Safety Features

- **Graceful Degradation**: If dependencies are missing, the feature is disabled without breaking the bot
- **Error Handling**: Network errors and API failures don't crash the bot
- **Rate Limiting**: Respects API rate limits for arXiv and Altmetric
- **Duplicate Prevention**: Tracks posted papers to avoid spam
- **Configurable Limits**: Prevents overwhelming channels with too many posts

## Troubleshooting

### "ArXiv tracker not available"
- Install missing dependencies: `pip install aiohttp`
- Check that `arxiv_tracker.py` exists in your bot directory

### "Auto-poster is disabled"
- Usually means missing dependencies
- Run `python test_arxiv.py` to diagnose issues

### No papers found
- arXiv might be temporarily unavailable
- Try increasing the `days` parameter
- Check your internet connection

### Altmetric data missing
- Altmetric API might be rate-limiting
- Use `--no-altmetric` flag for faster results
- Papers without Altmetric data will still be ranked by other factors

### Bot commands not working
- Make sure you're the bot owner (check `OWNER_ID` in config)
- Verify the bot has permission to post in the target channel
- Check bot logs for error messages

## API Rate Limits

- **arXiv API**: No official rate limit, but be respectful
- **Altmetric API**: Free tier allows reasonable usage
- **Built-in delays**: 1 second between Altmetric requests by default

## File Structure

```
multiverse-element-bot/
├── arxiv_tracker.py              # Core tracking functionality
├── arxiv_auto_poster.py          # Auto-posting system
├── test_arxiv.py                 # Test suite
├── README_arxiv.md               # This documentation
├── bot_commands.py               # Includes ArXiv commands
├── main.py                       # Includes ArXiv integration
├── baml_src/chat.baml           # Includes paper comment generation
└── arxiv_auto_poster_state.json # Auto-poster state (created automatically)
```

## Contributing

The ArXiv integration is designed to be:
- **Modular**: Can be easily disabled or removed
- **Extensible**: Easy to add new paper sources or ranking factors
- **Maintainable**: Clear separation of concerns and good error handling

Feel free to submit issues or pull requests to improve the functionality! 