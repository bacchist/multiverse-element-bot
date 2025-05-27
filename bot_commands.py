import niobot
from niobot import FileAttachment
from baml_client.sync_client import b

class BotCommands(niobot.Module):
    def __init__(self, bot):
        super().__init__(bot)
        self.crawler = getattr(bot, 'crawler', None)  # type: ignore

    @niobot.command()
    async def echo(self, ctx: niobot.Context, *, message: str):
        await ctx.respond("You said: " + message)

    @niobot.command()
    async def ping(self, ctx: niobot.Context):
        latency_ms = self.bot.latency(ctx.message)
        await ctx.respond(f"Pong! Latency: {latency_ms}ms")

    @niobot.command()
    async def read(self, ctx: niobot.Context, url: str):
        crawler = self.crawler
        result = await crawler.arun(url=url)  # type: ignore
        if result and hasattr(result, 'markdown'):
            article = b.ParseArticle(result.markdown)
            with open("article.txt", "w", encoding="utf-8") as f:
                f.write(f"Title: {article.title}\n\n")
                for paragraph in article.body:
                    f.write(f"{paragraph.text}\n\n")  # type: ignore
            attachment = await FileAttachment.from_file("article.txt")
            await ctx.respond("Here's a text version of that.", file=attachment)
        else:
            await ctx.respond("Failed to retrieve content from the URL.")

    @niobot.command()
    @niobot.is_owner()
    async def join_room(self, ctx, room: str):
        resp = await self.bot.join(room)
        if isinstance(resp, niobot.JoinResponse):
            await ctx.respond("joined " + room + " successfully.")
        else:
            await ctx.respond(f"Failed to join {room}: {resp}") 