"""Client initialization module for external services."""

from post_client import Poster
import bot_config

# Validate that required configuration is available
if not bot_config.API_TOKEN:
    raise ValueError("API_TOKEN is required but not set")

# Initialize the post client with configuration values
post_client = Poster(bot_config.API_URL, bot_config.API_TOKEN) 