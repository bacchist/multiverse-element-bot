import niobot
from niobot import FileAttachment
from baml_client.sync_client import b
import os
from pathlib import Path
import asyncio

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
        !chat_settings quirk <percentage> - Set quirk chance (0-100)
        """
        autonomous_chat = self.get_autonomous_chat()
        if not autonomous_chat:
            response = "Autonomous chat not available"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
        
        if action == "status":
            # Get room settings summary
            room_settings = autonomous_chat.get_room_status()
            enabled_count = sum(1 for enabled in room_settings.values() if enabled)
            disabled_count = len(room_settings) - enabled_count
            
            response = f"""🤖 **Autonomous Chat Settings:**
- Response interval: {autonomous_chat.min_response_interval.total_seconds() / 60:.1f} minutes
- Spontaneous check: {autonomous_chat.spontaneous_check_interval.total_seconds() / 60:.1f} minutes  
- History length: {autonomous_chat.max_history_length} messages
- Quirk chance: {autonomous_chat.quirk_chance * 100:.0f}%
- Rooms with history: {len(autonomous_chat.conversation_history)}

📋 **Room Settings:**
- Explicitly enabled: {enabled_count} rooms
- Explicitly disabled: {disabled_count} rooms
- Default for new rooms: Enabled

💾 Settings are automatically saved and persist across bot restarts."""
            
        elif action == "interval" and value:
            try:
                minutes = float(value)
                if minutes < 0.1:
                    response = "Interval must be at least 0.1 minutes (6 seconds)"
                else:
                    from datetime import timedelta
                    autonomous_chat.update_settings(min_response_interval=timedelta(minutes=minutes))
                    response = f"✅ Set minimum response interval to {minutes} minutes (saved)"
            except ValueError:
                response = "❌ Invalid number for interval"
                
        elif action == "spontaneous" and value:
            try:
                minutes = float(value)
                if minutes < 1:
                    response = "Spontaneous interval must be at least 1 minute"
                else:
                    from datetime import timedelta
                    autonomous_chat.update_settings(spontaneous_check_interval=timedelta(minutes=minutes))
                    response = f"✅ Set spontaneous check interval to {minutes} minutes (saved)"
            except ValueError:
                response = "❌ Invalid number for spontaneous interval"
                
        elif action == "history" and value:
            try:
                length = int(value)
                if length < 1 or length > 50:
                    response = "History length must be between 1 and 50 messages"
                else:
                    autonomous_chat.update_settings(max_history_length=length)
                    response = f"✅ Set conversation history length to {length} messages (saved)"
            except ValueError:
                response = "❌ Invalid number for history length"
                
        elif action == "quirk" and value:
            try:
                percentage = float(value)
                if percentage < 0 or percentage > 100:
                    response = "Quirk chance must be between 0 and 100 percent"
                else:
                    quirk_chance = percentage / 100.0
                    autonomous_chat.update_settings(quirk_chance=quirk_chance)
                    response = f"✅ Set quirk chance to {percentage}% (saved)"
            except ValueError:
                response = "❌ Invalid number for quirk percentage"
                
        else:
            response = """Usage:
!chat_settings status - Show current settings
!chat_settings interval <minutes> - Set response interval (e.g., 2.5)
!chat_settings spontaneous <minutes> - Set spontaneous check interval
!chat_settings history <number> - Set history length (1-50)
!chat_settings quirk <percentage> - Set quirk chance (0-100)

All settings are automatically saved and persist across bot restarts."""
        
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
        response = f"✅ Enabled autonomous chat in {room_name} (saved)"
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
        response = f"✅ Disabled autonomous chat in {room_name} (saved)"
        await ctx.respond(response)
        self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def chat_reset(self, ctx: niobot.Context, room_id: str = ""):
        """Reset a room to default chat settings (remove explicit enable/disable). Owner only."""
        autonomous_chat = self.get_autonomous_chat()
        if not autonomous_chat:
            response = "❌ Autonomous chat not available"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            return
        
        target_room_id = room_id if room_id else ctx.room.room_id
        room_name = ctx.room.display_name or ctx.room.name if not room_id else room_id
        
        # Remove the room from explicit settings
        if target_room_id in autonomous_chat.enabled_rooms:
            del autonomous_chat.enabled_rooms[target_room_id]
            autonomous_chat.save_settings()
            response = f"✅ Reset {room_name} to default chat settings (enabled)"
        else:
            response = f"ℹ️ {room_name} already uses default settings"
        
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

    @niobot.command()
    @niobot.is_owner()
    async def trending_ai(self, ctx: niobot.Context, days: int = 3, count: int = 5):
        """Fetch trending AI papers from arXiv ranked by Altmetric scores. Owner only.
        
        Usage:
        !trending_ai - Get top 5 papers from last 3 days
        !trending_ai 7 10 - Get top 10 papers from last 7 days
        """
        try:
            # Import the tracker (lazy import to avoid startup issues)
            try:
                from arxiv_tracker import ArxivAltmetricTracker
            except ImportError:
                response = "❌ ArXiv tracker not available. Missing dependencies or module not installed."
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            # Validate parameters
            days = max(1, min(days, 30))  # Limit to 1-30 days
            count = max(1, min(count, 20))  # Limit to 1-20 papers
            
            response = f"🔍 Fetching trending AI papers from the last {days} days..."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
            # Initialize tracker and fetch papers
            async with ArxivAltmetricTracker() as tracker:
                papers = await tracker.get_trending_papers(
                    days_back=days,
                    count=count,
                    include_altmetric=True
                )
            
            if not papers:
                response = "❌ No AI papers found in the specified time range."
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            # Format and send results
            header = f"🤖 **Top {len(papers)} Trending AI Papers** (Last {days} days)\n\n"
            await ctx.respond(header)
            self._log_bot_response(ctx, header)
            
            # Send each paper as a separate message to avoid length limits
            for i, paper in enumerate(papers, 1):
                paper_summary = self._format_paper_for_matrix(paper, i)
                await ctx.respond(paper_summary)
                self._log_bot_response(ctx, f"Paper #{i}: {paper.title[:50]}...")
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
            
            # Summary message
            summary = f"\n📈 **Summary**: Displayed top {len(papers)} papers"
            if any(p.altmetric_score and p.altmetric_score > 0 for p in papers):
                avg_score = sum(p.altmetric_score or 0 for p in papers) / len(papers)
                summary += f"\n📊 Average Altmetric score: {avg_score:.1f}"
            
            await ctx.respond(summary)
            self._log_bot_response(ctx, summary)
            
        except Exception as e:
            response = f"❌ Error fetching AI papers: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
    
    def _format_paper_for_matrix(self, paper, rank: int) -> str:
        """Format a paper for Matrix display with proper markdown."""
        # Truncate title for readability
        title = paper.title[:80] + "..." if len(paper.title) > 80 else paper.title
        
        # Format authors (show first 3)
        if len(paper.authors) <= 3:
            authors_str = ", ".join(paper.authors)
        else:
            authors_str = ", ".join(paper.authors[:3]) + f" et al. ({len(paper.authors)} total)"
        
        # Truncate authors if too long
        if len(authors_str) > 100:
            authors_str = authors_str[:97] + "..."
        
        # Altmetric info
        altmetric_info = ""
        if paper.altmetric_score and paper.altmetric_score > 0:
            altmetric_info = f"📊 Altmetric: **{paper.altmetric_score:.1f}**"
            
            if paper.altmetric_data:
                mentions = []
                if paper.altmetric_data.get('cited_by_tweeters_count', 0) > 0:
                    mentions.append(f"{paper.altmetric_data['cited_by_tweeters_count']} tweets")
                if paper.altmetric_data.get('cited_by_posts_count', 0) > 0:
                    mentions.append(f"{paper.altmetric_data['cited_by_posts_count']} posts")
                if paper.altmetric_data.get('cited_by_rdts_count', 0) > 0:
                    mentions.append(f"{paper.altmetric_data['cited_by_rdts_count']} Reddit")
                
                if mentions:
                    altmetric_info += f" ({', '.join(mentions)})"
        else:
            altmetric_info = "📊 Altmetric: No data"
        
        # Categories (show main AI categories only)
        ai_categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "stat.ML"]
        main_categories = [cat for cat in paper.categories if cat in ai_categories]
        categories_str = ", ".join(main_categories[:2])  # Show max 2 categories
        
        # Truncate abstract
        abstract = paper.abstract[:150] + "..." if len(paper.abstract) > 150 else paper.abstract
        
        # Format the message
        message = f"""**#{rank}. {title}**

👥 {authors_str}
📅 {paper.published.strftime('%Y-%m-%d')} | 🏷️ {categories_str}
{altmetric_info}

{abstract}

🔗 [arXiv]({paper.arxiv_url}) | [PDF]({paper.pdf_url})"""
        
        return message

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_status(self, ctx: niobot.Context):
        """Show status of the arXiv auto-poster. Owner only."""
        try:
            auto_poster = getattr(self.bot, 'arxiv_auto_poster', None)
            if not auto_poster:
                response = "❌ ArXiv auto-poster not initialized"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            status = auto_poster.get_status()
            
            response = f"""📊 **ArXiv Auto-Poster Status**

**Enabled**: {status['enabled']}
**Queue**: {status['queue_size']} papers waiting
**Posted**: {status['posted_total']} total papers
**Today**: {status['posts_today']}/{status['max_posts_per_day']} posts
**Target**: {status['target_channel']}

**Last Discovery**: {status['last_discovery'] or 'Never'}
**Last Posting**: {status['last_posting'] or 'Never'}

**Next Discovery**: {status['next_discovery'] or 'Not scheduled'}
**Next Posting**: {status['next_posting'] or 'Not scheduled'}"""
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error getting auto-poster status: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_discover(self, ctx: niobot.Context, days: int = 3):
        """Manually trigger arXiv paper discovery. Owner only."""
        try:
            auto_poster = getattr(self.bot, 'arxiv_auto_poster', None)
            if not auto_poster:
                response = "❌ ArXiv auto-poster not initialized"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            if not auto_poster.enabled:
                response = "❌ ArXiv auto-poster is disabled (missing dependencies)"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            days = max(1, min(days, 30))  # Limit to 1-30 days
            
            response = f"🔍 Starting manual discovery for last {days} days..."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
            new_papers = await auto_poster.discover_papers(days_back=days)
            
            response = f"✅ Discovery complete! Found {new_papers} new papers. Queue now has {len(auto_poster.queue)} papers."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error during discovery: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_post(self, ctx: niobot.Context):
        """Manually trigger posting the next paper from queue. Owner only."""
        try:
            auto_poster = getattr(self.bot, 'arxiv_auto_poster', None)
            if not auto_poster:
                response = "❌ ArXiv auto-poster not initialized"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            if not auto_poster.enabled:
                response = "❌ ArXiv auto-poster is disabled (missing dependencies)"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            if not auto_poster.queue:
                response = "📭 No papers in queue to post"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            response = f"📤 Posting next paper from queue..."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
            success = await auto_poster.post_next_paper()
            
            if success:
                response = f"✅ Paper posted successfully! Queue now has {len(auto_poster.queue)} papers remaining."
            else:
                response = f"❌ Failed to post paper. Check logs for details."
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error posting paper: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_queue(self, ctx: niobot.Context, count: int = 5):
        """Show papers in the posting queue. Owner only."""
        try:
            auto_poster = getattr(self.bot, 'arxiv_auto_poster', None)
            if not auto_poster:
                response = "❌ ArXiv auto-poster not initialized"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            if not auto_poster.queue:
                response = "📭 Queue is empty"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            count = max(1, min(count, 10))  # Limit to 1-10 papers
            queue_papers = auto_poster.queue[:count]
            
            response = f"📋 **Top {len(queue_papers)} Papers in Queue** (of {len(auto_poster.queue)} total)\n\n"
            
            for i, paper in enumerate(queue_papers, 1):
                response += f"**#{i}. {paper.title[:60]}{'...' if len(paper.title) > 60 else ''}**\n"
                response += f"   Priority: {paper.priority_score:.1f} | Altmetric: {paper.altmetric_score or 0:.1f}\n"
                response += f"   Categories: {', '.join(paper.categories[:2])}\n"
                response += f"   🔗 {paper.arxiv_url}\n\n"
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error showing queue: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_config(self, ctx: niobot.Context, setting: str = "", value: str = ""):
        """Configure arXiv auto-poster settings. Owner only.
        
        Usage:
        !arxiv_config - Show current settings
        !arxiv_config channel #new-channel:server.com - Change target channel
        !arxiv_config max_posts 3 - Set max posts per day
        !arxiv_config interval 4 - Set posting interval in hours
        """
        try:
            auto_poster = getattr(self.bot, 'arxiv_auto_poster', None)
            if not auto_poster:
                response = "❌ ArXiv auto-poster not initialized"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            if not setting:
                # Show current settings
                response = f"""⚙️ **ArXiv Auto-Poster Configuration**

**Enabled**: {auto_poster.enabled}
**Target Channel**: {auto_poster.target_channel}
**Max Posts/Day**: {auto_poster.max_posts_per_day}
**Posting Interval**: {auto_poster.posting_interval.total_seconds() / 3600:.1f} hours
**Discovery Interval**: {auto_poster.discovery_interval.total_seconds() / 3600:.1f} hours

Use `!arxiv_config <setting> <value>` to change settings."""
                
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            # Update settings
            if setting == "channel" and value:
                auto_poster.target_channel = value
                response = f"✅ Target channel set to: {value}"
                
            elif setting == "max_posts" and value:
                try:
                    max_posts = int(value)
                    if 1 <= max_posts <= 20:
                        auto_poster.max_posts_per_day = max_posts
                        response = f"✅ Max posts per day set to: {max_posts}"
                    else:
                        response = "❌ Max posts must be between 1 and 20"
                except ValueError:
                    response = "❌ Invalid number for max posts"
                    
            elif setting == "interval" and value:
                try:
                    hours = float(value)
                    if 0.5 <= hours <= 24:
                        from datetime import timedelta
                        auto_poster.posting_interval = timedelta(hours=hours)
                        response = f"✅ Posting interval set to: {hours} hours"
                    else:
                        response = "❌ Interval must be between 0.5 and 24 hours"
                except ValueError:
                    response = "❌ Invalid number for interval"
                    
            else:
                response = """❌ Invalid setting. Available settings:
- channel <#channel:server.com>
- max_posts <1-20>
- interval <0.5-24 hours>"""
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error configuring auto-poster: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response) 