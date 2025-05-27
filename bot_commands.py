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
    
    def get_autonomous_chat(self):
        """Get autonomous_chat instance from bot object safely."""
        return getattr(self.bot, 'autonomous_chat', None)

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
        """Join a room by ID, alias, or name. Owner only.
        
        Examples:
        !join_room #room-name:server.com
        !join_room !roomid:server.com
        !join_room room-name (will try #room-name:themultiverse.school)
        """
        # If it doesn't look like a full room ID or alias, try to make it one
        original_room = room
        if not room.startswith(('!', '#')) and ':' not in room:
            # Try as an alias first
            room = f"#{room}:themultiverse.school"
        
        try:
            resp = await self.bot.join(room)
            if isinstance(resp, niobot.JoinResponse):
                response = f"✅ Successfully joined {original_room}"
                if room != original_room:
                    response += f" (as {room})"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                
                # Show the new room in the list if successful
                if hasattr(self.bot, 'rooms') and resp.room_id in self.bot.rooms:
                    room_obj = self.bot.rooms[resp.room_id]
                    room_name = getattr(room_obj, 'display_name', None) or getattr(room_obj, 'name', None)
                    member_count = getattr(room_obj, 'member_count', 'Unknown')
                    
                    additional_info = f"\n📋 **{room_name or resp.room_id}**\n"
                    additional_info += f"   ID: `{resp.room_id}`\n"
                    additional_info += f"   Members: {member_count}"
                    
                    await ctx.respond(additional_info)
                    self._log_bot_response(ctx, additional_info)
            else:
                error_msg = str(resp)
                suggestions = []
                
                if "not legal room ID" in error_msg:
                    suggestions.append(f"Try: `!join_room #{original_room}:themultiverse.school`")
                    suggestions.append(f"Or use a full room ID like: `!join_room !roomid:server.com`")
                elif "not found" in error_msg or "unknown" in error_msg.lower():
                    suggestions.append("The room might not exist or might be private")
                    suggestions.append("Check the room name/alias spelling")
                elif "forbidden" in error_msg.lower():
                    suggestions.append("You might not have permission to join this room")
                    suggestions.append("The room might be invite-only")
                
                response = f"❌ Failed to join '{original_room}': {error_msg}"
                if suggestions:
                    response += f"\n\n💡 Suggestions:\n" + "\n".join(f"   • {s}" for s in suggestions)
                
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                
        except Exception as e:
            response = f"❌ Error joining '{original_room}': {str(e)}"
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
        autonomous_chat = self.get_autonomous_chat()
        if not autonomous_chat:
            response = "Autonomous chat not available"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
        
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
        autonomous_chat = self.get_autonomous_chat()
        if not autonomous_chat:
            response = "Autonomous chat not available"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
            
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

    @niobot.command()
    @niobot.is_owner()
    async def chat_enable(self, ctx: niobot.Context, room_id: str = ""):
        """Enable autonomous chat in a room. Use current room if no room_id provided. Owner only."""
        autonomous_chat = self.get_autonomous_chat()
        if not autonomous_chat:
            response = "Autonomous chat not available"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
        
        target_room_id = room_id if room_id else ctx.room.room_id
        room_name = ctx.room.display_name or ctx.room.name if not room_id else room_id
        
        autonomous_chat.enable_room(target_room_id)
        response = f"Enabled autonomous chat in {room_name}"
        await ctx.respond(response)
        self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def chat_disable(self, ctx: niobot.Context, room_id: str = ""):
        """Disable autonomous chat in a room. Use current room if no room_id provided. Owner only."""
        autonomous_chat = self.get_autonomous_chat()
        if not autonomous_chat:
            response = "Autonomous chat not available"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
        
        target_room_id = room_id if room_id else ctx.room.room_id
        room_name = ctx.room.display_name or ctx.room.name if not room_id else room_id
        
        autonomous_chat.disable_room(target_room_id)
        response = f"Disabled autonomous chat in {room_name}"
        await ctx.respond(response)
        self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def list_rooms(self, ctx: niobot.Context):
        """List all rooms/channels the bot is currently in with autonomous chat settings. Owner only."""
        autonomous_chat = self.get_autonomous_chat()
        
        # Start with autonomous chat settings
        if autonomous_chat:
            response = f"""🤖 **Autonomous Chat Settings:**
- Response interval: {autonomous_chat.min_response_interval.total_seconds() / 60:.1f} minutes
- Spontaneous check: {autonomous_chat.spontaneous_check_interval.total_seconds() / 60:.1f} minutes  
- History length: {autonomous_chat.max_history_length} messages
- Quirk chance: {autonomous_chat.quirk_chance * 100:.0f}%

"""
        else:
            response = "❌ Autonomous chat not available\n\n"
        
        # Add rooms information
        if not hasattr(ctx.bot, 'rooms'):
            response += "❌ Bot rooms information not available"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
        
        rooms = ctx.bot.rooms
        if not rooms:
            response += "📭 Bot is not currently in any rooms"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
        
        current_room_id = ctx.room.room_id
        response += f"📋 **Bot is currently in {len(rooms)} room(s):**\n\n"
        
        for room_id, room_obj in rooms.items():
            room_name = getattr(room_obj, 'display_name', None) or getattr(room_obj, 'name', None)
            member_count = getattr(room_obj, 'member_count', 'Unknown')
            
            # Get autonomous chat status for this room
            if autonomous_chat:
                chat_enabled = autonomous_chat.is_enabled_in_room(room_id)
                chat_status = "🤖 Chat enabled" if chat_enabled else "🔇 Chat disabled"
            else:
                chat_status = "❓ Chat status unknown"
            
            # Mark current room
            current_marker = " 👈 *current*" if room_id == current_room_id else ""
            
            if room_name:
                response += f"📋 **{room_name}**{current_marker}\n"
            else:
                response += f"📋 **{room_id}**{current_marker}\n"
            
            response += f"   ID: `{room_id}`\n"
            response += f"   Members: {member_count}\n"
            response += f"   Status: {chat_status}\n\n"
        
        await ctx.respond(response)
        self._log_bot_response(ctx, response) 