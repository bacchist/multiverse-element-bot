# ArXiv AI Paper Tracker

A standalone command-line tool that fetches new AI papers from arXiv and ranks them by popularity using the Altmetric API.

## Features

- 🔍 **Smart Search**: Searches across all major AI categories (cs.AI, cs.LG, cs.CL, cs.CV, cs.NE, stat.ML)
- 📊 **Popularity Ranking**: Uses Altmetric scores to rank papers by social media mentions and citations
- 🎯 **Flexible Filtering**: Filter by date range, categories, and result count
- 📄 **Multiple Output Formats**: Terminal, Markdown, and JSON output
- 💾 **Export Results**: Save results to JSON files for further processing
- ⚡ **Fast Mode**: Skip Altmetric data for faster results

## Installation

Make sure you have Python 3.13+ and the required dependencies:

```bash
# Install dependencies
pip install aiohttp

# Or if using the full bot environment
pip install -r requirements.txt
```

## Quick Start

```bash
# Basic usage - get top 5 papers from last 3 days
python arxiv_tracker.py

# Get top 10 papers from last week
python arxiv_tracker.py --days 7 --count 10

# Fast mode (no Altmetric data)
python arxiv_tracker.py --days 3 --count 5 --no-altmetric

# Save results to file
python arxiv_tracker.py --days 1 --output today_papers.json
```

## Command Line Options

```
usage: arxiv_tracker.py [-h] [--days DAYS] [--count COUNT] [--max-results MAX_RESULTS]
                        [--output OUTPUT] [--no-altmetric] [--categories {cs.AI,cs.LG,cs.CL,cs.CV,cs.NE,stat.ML} ...]
                        [--format {terminal,markdown,json}] [--verbose]

Fetch and rank AI papers from arXiv using Altmetric scores

options:
  -h, --help            show this help message and exit
  --days DAYS, -d DAYS  Number of days back to search (default: 3, max: 30)
  --count COUNT, -c COUNT
                        Number of top papers to display (default: 5, max: 50)
  --max-results MAX_RESULTS, -m MAX_RESULTS
                        Maximum papers to fetch from arXiv (default: 100)
  --output OUTPUT, -o OUTPUT
                        Save results to JSON file (optional)
  --no-altmetric        Skip Altmetric data fetching (faster but no popularity ranking)
  --categories {cs.AI,cs.LG,cs.CL,cs.CV,cs.NE,stat.ML} ...
                        Specific categories to search (default: all AI categories)
  --format {terminal,markdown,json}
                        Output format (default: terminal)
  --verbose, -v         Verbose output with debug information
```

## Examples

### Basic Usage
```bash
# Default: top 5 papers from last 3 days
python arxiv_tracker.py

# Get more papers from a longer time period
python arxiv_tracker.py --days 7 --count 15
```

### Category Filtering
```bash
# Only Machine Learning papers
python arxiv_tracker.py --categories cs.LG

# AI and Computer Vision papers
python arxiv_tracker.py --categories cs.AI cs.CV --days 5
```

### Output Formats
```bash
# Markdown format (great for documentation)
python arxiv_tracker.py --format markdown --days 2 --count 5

# JSON format (for programmatic use)
python arxiv_tracker.py --format json --days 1 --count 10

# Save to file
python arxiv_tracker.py --output weekly_papers.json --days 7
```

### Performance Options
```bash
# Fast mode - skip Altmetric data (much faster)
python arxiv_tracker.py --no-altmetric --days 7 --count 20

# Verbose mode for debugging
python arxiv_tracker.py --verbose --days 1 --count 3
```

## Output Explanation

### Terminal Format
The default terminal output shows:
- **Paper Title** and ranking number
- **Authors** (first 3, with total count if more)
- **Publication Date** and **Categories**
- **Altmetric Score** with breakdown of mentions (tweets, posts, Reddit)
- **Abstract** (truncated)
- **Links** to arXiv page and PDF

### Altmetric Scores
- **Score > 10**: High social media attention
- **Score 5-10**: Moderate attention  
- **Score 1-5**: Some mentions
- **Score 0 or No data**: Little to no social media activity

### Categories
- **cs.AI**: Artificial Intelligence
- **cs.LG**: Machine Learning
- **cs.CL**: Computation and Language (NLP)
- **cs.CV**: Computer Vision and Pattern Recognition
- **cs.NE**: Neural and Evolutionary Computing
- **stat.ML**: Machine Learning (Statistics)

## Testing

Run the test script to verify everything works:

```bash
python test_arxiv.py
```

This will run several quick tests to ensure the tracker is working properly.

## Rate Limiting

The script respects API rate limits:
- **arXiv API**: 3 seconds between requests
- **Altmetric API**: 1 second between requests

For large queries, the script may take several minutes to complete when fetching Altmetric data.

## Integration with Matrix Bot

This script is also integrated into the Matrix bot as the `!trending_ai` command. The standalone version is useful for:
- Testing and development
- Batch processing
- Generating reports
- Integration with other tools

## Troubleshooting

### Common Issues

1. **No papers found**: Try increasing the `--days` parameter or checking if arXiv is accessible
2. **Slow performance**: Use `--no-altmetric` flag for faster results
3. **Network errors**: Check internet connection and try again
4. **JSON parsing errors**: Usually temporary arXiv API issues, try again later

### Debug Mode
Use `--verbose` flag to see detailed information about what the script is doing:

```bash
python arxiv_tracker.py --verbose --days 1 --count 2
```

## License

This tool is part of the multiverse-element-bot project. 