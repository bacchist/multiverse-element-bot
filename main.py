import niobot
import logging
import config
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from baml_client.sync_client import b
from niobot import FileAttachment

logging.basicConfig(level=logging.INFO, filename="bot.log")
url_file = open("urls.txt", "w")

bot = niobot.NioBot(
    homeserver=config.HOMESERVER,
    user_id=config.USER_ID,
    device_id='topdesk',
    store_path='./store',
    command_prefix="!",
    owner_id="@marshall:themultiverse.school"
)

@bot.on_event("ready")
async def on_ready(_):
    # That first argument is needed as the first result of the sync loop is passed to ready. Without it, this event
    # will fail to fire, and will cause a potentially catasrophic failure.
    print("Bot is ready!")


@bot.command(name="ping")
async def ping(ctx: niobot.Context):
    latency_ms = bot.latency(ctx.message)
    await ctx.respond("Pong! Latency: %dms" % latency_ms)

@bot.on_event("command_error")
async def on_command_error(ctx: niobot.Context, error: Exception):
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await ctx.respond(f"[{timestamp}] An error occurred while processing your command. Please try again later.")
    logging.error(f"[{timestamp}] Command error: {error}", exc_info=True)

@bot.on_event("command")
async def on_command(ctx):
    print("User {} ran command {}".format(ctx.message.sender, ctx.message.command.name))

@bot.on_event("message")
async def on_message(room, message):
    if isinstance(message, niobot.RoomMessage):
        print(f"{message.sender} said: {message}")
        if "http://" in message.body or "https://" in message.body:
            # Extract URL from message
            words = message.body.split()
            for word in words:
                if word.startswith(("http://", "https://")):
                    url_file.write(word + "\n")
                    url_file.flush()

# A command with arguments
@bot.command()
async def echo(ctx: niobot.Context, *, message: str):
    await ctx.respond("You said: " + message)

@bot.command(name="read")
async def forward(ctx: niobot.Context, url: str):
    config = CrawlerRunConfig(
        check_robots_txt=False,
        magic=True,
        remove_overlay_elements=True,
        page_timeout=60000,
        cache_mode=CacheMode.BYPASS
    )
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        if result and hasattr(result, 'markdown'):
            article = b.ParseArticle(result.markdown)
            with open("article.txt", "w", encoding="utf-8") as f:
                f.write(f"Title: {article.title}\n\n")
                for paragraph in article.body:
                    f.write(f"{paragraph.text}\n\n")
            attachment = await FileAttachment.from_file("article.txt")
            await ctx.respond("Here's a text version of that.", file=attachment)
        else:
            await ctx.respond("Failed to retrieve content from the URL.")

bot.run(access_token=config.ACCESS_TOKEN)