import os
import niobot
import logging
import config
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode
from baml_client.sync_client import b
from niobot import FileAttachment
import requests
import asyncio

logging.basicConfig(level=logging.INFO, filename="bot.log")

bot = niobot.NioBot(
    homeserver=config.HOMESERVER,
    user_id=config.USER_ID,
    device_id='topdesk',
    store_path='./store',
    command_prefix="!",
    owner_id="@marshall:themultiverse.school"
)


browser_config = BrowserConfig(
)
crawler = AsyncWebCrawler(config=browser_config)

@bot.on_event("ready")
async def on_ready(_):
    print("Bot is ready!")

@bot.on_event("command")
async def on_command(ctx):
    print("User {} ran command {}".format(ctx.message.sender, ctx.message.command.name))

# A command with arguments
@bot.command()
async def echo(ctx: niobot.Context, *, message: str):
    await ctx.respond("You said: " + message)

@bot.on_event("command_error")
async def on_command_error(ctx: niobot.Context, error: Exception):
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await ctx.respond(f"[{timestamp}] An error occurred while processing your command. Please try again later.")
    logging.error(f"[{timestamp}] Command error: {error}", exc_info=True)

@bot.command(name="ping")
async def ping(ctx: niobot.Context):
    latency_ms = bot.latency(ctx.message)
    await ctx.respond("Pong! Latency: %dms" % latency_ms)

@bot.on_event("message")
async def on_message(room, message):
    if isinstance(message, niobot.RoomMessage):
        # Check if message is more than an hour old
        from datetime import datetime, timezone
        message_time = datetime.fromtimestamp(message.server_timestamp / 1000, timezone.utc)
        now = datetime.now(timezone.utc)
        if (now - message_time).total_seconds() > 3600:  # More than 1 hour
            return

        print(f"{message.sender} said: {message}")
        if "http://" in message.body or "https://" in message.body:
            words = message.body.split()
            for word in words:
                if word.startswith(("http://", "https://")):
                    try:
                        await crawler.start()
                        result = await crawler.arun(url=word)
                        if result and hasattr(result, 'markdown'):
                            article = b.ParseArticle(result.markdown)
                            summary = b.WriteArticleSummary(article)
                            with open("urls.txt", "a", encoding="utf-8") as url_file:
                                url_file.write(f"{word}\t{summary}\n")
                            post = b.WritePost(summary=summary.summary, url=word)
                            api_url = config.API_URL
                            token = config.API_TOKEN
                            headers = {
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {token}"
                            }
                            data = {
                                "content": post.text if hasattr(post, 'text') else str(post),
                                "url": post.url if hasattr(post, 'url') else word
                            }
                            def do_post():
                                return requests.post(api_url, headers=headers, json=data, allow_redirects=True)
                            resp = await asyncio.to_thread(do_post)
                            if resp.status_code in (200, 201):
                                print(f"Posted to API: {word}")
                            else:
                                print(f"Failed to post to API: {resp.status_code} {resp.text}")
                        else:
                            with open("urls.txt", "a", encoding="utf-8") as url_file:
                                url_file.write(f"{word}\t[Could not fetch article content]\n")
                    except Exception as e:
                        with open("urls.txt", "a", encoding="utf-8") as url_file:
                            url_file.write(f"{word}\t[Error: {str(e)}]\n")

@bot.command(name="read")
async def forward(ctx: niobot.Context, url: str):
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

@bot.command()
@niobot.is_owner()
async def join_room(ctx, room: str):
    resp = await bot.join(room)
    if isinstance(resp, niobot.JoinResponse):
        await ctx.respond("joined " + room + " successfully.")
    else:
        await ctx.respond(f"Failed to join {room}: {resp}")


bot.run(access_token=config.ACCESS_TOKEN)