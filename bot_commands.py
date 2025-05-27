import niobot
from niobot import FileAttachment
from baml_client.sync_client import b
import os
from pathlib import Path

class BotCommands(niobot.Module):
    def __init__(self, bot):
        super().__init__(bot)
        self.crawler = getattr(bot, 'crawler', None)  # type: ignore
        # Import chat_logger here to avoid circular imports
        from chat_logger import ChatLogger
        self.chat_logger = ChatLogger()

    def _log_bot_response(self, ctx: niobot.Context, response_text: str):
        """Helper method to log bot responses."""
        room_name = getattr(ctx.room, 'display_name', None) or getattr(ctx.room, 'name', None)
        self.chat_logger.log_message(
            ctx.room.room_id,
            room_name,
            ctx.bot.user_id,
            response_text,
            "m.text"
        )

    @niobot.command()
    async def echo(self, ctx: niobot.Context, *, message: str):
        response = "You said: " + message
        await ctx.respond(response)
        self._log_bot_response(ctx, response)

    @niobot.command()
    async def ping(self, ctx: niobot.Context):
        latency_ms = self.bot.latency(ctx.message)
        response = f"Pong! Latency: {latency_ms}ms"
        await ctx.respond(response)
        self._log_bot_response(ctx, response)

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
            response = "Here's a text version of that."
            await ctx.respond(response, file=attachment)
            self._log_bot_response(ctx, f"{response} [FILE: article.txt]")
        else:
            response = "Failed to retrieve content from the URL."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def join_room(self, ctx, room: str):
        resp = await self.bot.join(room)
        if isinstance(resp, niobot.JoinResponse):
            response = "joined " + room + " successfully."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
        else:
            response = f"Failed to join {room}: {resp}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def logs(self, ctx: niobot.Context, lines: int = 50):
        """Show recent chat logs for this room. Owner only."""
        room_name = getattr(ctx.room, 'display_name', None) or getattr(ctx.room, 'name', None)
        safe_room_name = self.chat_logger._get_safe_room_name(ctx.room.room_id, room_name)
        log_file = Path("chat_logs") / f"{safe_room_name}.log"
        
        if not log_file.exists():
            response = "No chat logs found for this room yet."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
        
        try:
            # Read the last N lines from the log file
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            if not recent_lines:
                response = "Chat log file is empty."
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            # Create a temporary file with recent logs
            temp_log_file = f"recent_logs_{ctx.room.room_id.replace(':', '_').replace('!', '')}.txt"
            with open(temp_log_file, 'w', encoding='utf-8') as f:
                f.write(f"Recent {len(recent_lines)} lines from {room_name or ctx.room.room_id}:\n\n")
                f.writelines(recent_lines)
            
            attachment = await FileAttachment.from_file(temp_log_file)
            response = f"Here are the last {len(recent_lines)} lines from this room's chat log."
            await ctx.respond(response, file=attachment)
            self._log_bot_response(ctx, f"{response} [FILE: {temp_log_file}]")
            
            # Clean up temp file
            os.remove(temp_log_file)
            
        except Exception as e:
            response = f"Error reading chat logs: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def chat_settings(self, ctx: niobot.Context, action: str = "status", value: str = ""):
        """Control autonomous chat settings. Owner only.
        
        Usage:
        !chat_settings status - Show current settings
        !chat_settings interval <minutes> - Set minimum response interval
        !chat_settings spontaneous <minutes> - Set spontaneous check interval
        !chat_settings history <number> - Set conversation history length
        """
        # Get the autonomous chat instance from main module
        import main
        autonomous_chat = main.autonomous_chat
        
        if action == "status":
            response = f"""Autonomous Chat Settings:
- Response interval: {autonomous_chat.min_response_interval.total_seconds() / 60:.1f} minutes
- Spontaneous check: {autonomous_chat.spontaneous_check_interval.total_seconds() / 60:.1f} minutes  
- History length: {autonomous_chat.max_history_length} messages
- Rooms with history: {len(autonomous_chat.conversation_history)}"""
            
        elif action == "interval" and value:
            try:
                minutes = float(value)
                from datetime import timedelta
                autonomous_chat.min_response_interval = timedelta(minutes=minutes)
                response = f"Set minimum response interval to {minutes} minutes"
            except ValueError:
                response = "Invalid number for interval"
                
        elif action == "spontaneous" and value:
            try:
                minutes = float(value)
                from datetime import timedelta
                autonomous_chat.spontaneous_check_interval = timedelta(minutes=minutes)
                response = f"Set spontaneous check interval to {minutes} minutes"
            except ValueError:
                response = "Invalid number for spontaneous interval"
                
        elif action == "history" and value:
            try:
                length = int(value)
                autonomous_chat.max_history_length = max(1, min(50, length))  # Limit between 1-50
                response = f"Set conversation history length to {autonomous_chat.max_history_length} messages"
            except ValueError:
                response = "Invalid number for history length"
                
        else:
            response = """Usage:
!chat_settings status - Show current settings
!chat_settings interval <minutes> - Set response interval (e.g., 2.5)
!chat_settings spontaneous <minutes> - Set spontaneous check interval
!chat_settings history <number> - Set history length (1-50)"""
        
        await ctx.respond(response)
        self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner() 
    async def force_spontaneous(self, ctx: niobot.Context):
        """Force the bot to consider sending a spontaneous message in this room. Owner only."""
        import main
        autonomous_chat = main.autonomous_chat
        room_name = getattr(ctx.room, 'display_name', None) or getattr(ctx.room, 'name', None)
        
        try:
            message = await autonomous_chat.check_spontaneous_message(ctx.room.room_id, room_name)
            if message:
                await ctx.respond(message)
                self._log_bot_response(ctx, message)
                response = "Sent spontaneous message"
            else:
                response = "Bot decided not to send a spontaneous message right now"
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"Error generating spontaneous message: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response) 