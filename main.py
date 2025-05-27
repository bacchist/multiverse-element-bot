import niobot
import logging
import config
from crawl4ai import AsyncWebCrawler, BrowserConfig
from actions import process_url
from bot_commands import BotCommands
from crawling import set_crawler
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, filename="bot.log")

bot = niobot.NioBot(
    homeserver=config.HOMESERVER,
    user_id=config.USER_ID,
    device_id='topdesk',
    store_path='./store',
    command_prefix="!",
    owner_id="@marshall:themultiverse.school"
)

browser_config = BrowserConfig()
crawler = AsyncWebCrawler(config=browser_config)
set_crawler(crawler)
bot.crawler = crawler  # Attach crawler to bot for module access  # type: ignore

bot.mount_module("bot_commands")

@bot.on_event("ready")
async def on_ready(_):
    print("Bot is ready!")

@bot.on_event("command")
async def on_command(ctx):
    print("User {} ran command {}".format(ctx.message.sender, ctx.message.command.name))

@bot.on_event("command_error")
async def on_command_error(ctx: niobot.Context, error: Exception):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await ctx.respond(f"[{timestamp}] An error occurred while processing your command. Please try again later.")
    logging.error(f"[{timestamp}] Command error: {error}", exc_info=True)

@bot.on_event("message")
async def on_message(room, message):
    print(f"Observed message from {getattr(message, 'sender', 'unknown')}: {getattr(message, 'body', str(message))}")
    message_time = datetime.fromtimestamp(getattr(message, 'server_timestamp', 0) / 1000, timezone.utc)
    now = datetime.now(timezone.utc)
    if (now - message_time).total_seconds() > 3600:
        print("Message is stale; ignoring.")
        return
    body = getattr(message, 'body', '')
    url = next((word for word in body.split() if word.startswith(("http://", "https://"))), None)
    if not url:
        print("No URL found in message; ignoring.")
        return
    print(f"Processing URL: {url}")
    try:
        await process_url(url)
    except Exception as e:
        print(f"Exception during URL processing: {e}")

bot.run(access_token=config.ACCESS_TOKEN)