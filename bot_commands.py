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
        # Add trending context if noteworthy
        trending_context = ""
        if paper.altmetric_score and paper.altmetric_score >= 5.0:
            trending_context = f" (🔥 Trending: {paper.altmetric_score:.0f} Altmetric score)"
        elif paper.altmetric_data:
            tweets = paper.altmetric_data.get('cited_by_tweeters_count', 0)
            reddit = paper.altmetric_data.get('cited_by_rdts_count', 0)
            news = paper.altmetric_data.get('cited_by_feeds_count', 0)
            
            if tweets >= 10:
                trending_context = f" (🐦 {tweets} tweets)"
            elif reddit >= 3:
                trending_context = f" (🔴 Popular on Reddit)"
            elif news >= 2:
                trending_context = f" (📰 News coverage)"
        
        # Generate a brief insight about the paper
        try:
            from baml_client.sync_client import b
            
            authors_str = ", ".join(paper.authors[:2])
            categories_str = ", ".join(paper.categories[:2])
            
            trending_info = ""
            if paper.altmetric_score and paper.altmetric_score >= 5.0:
                trending_info = f"High social engagement (Altmetric: {paper.altmetric_score:.1f}). "
            
            result = b.GeneratePaperComment(
                title=paper.title,
                authors=authors_str,
                abstract=paper.abstract[:400],
                categories=categories_str,
                altmetric_info=trending_info,
                context="Generate a concise, insightful comment (1-2 sentences) about why this research is interesting or significant."
            )
            
            comment = result.comment
            
        except Exception:
            # Fallback comment
            if any(cat in ['cs.AI', 'cs.LG'] for cat in paper.categories):
                comment = "Interesting new approach in AI/ML research."
            elif 'cs.CL' in paper.categories:
                comment = "New developments in natural language processing."
            elif 'cs.CV' in paper.categories:
                comment = "Novel computer vision research with potential applications."
            else:
                comment = "New research gaining attention in the AI community."
        
        # Format the message concisely
        message = f"""**#{rank}. {paper.title}**{trending_context}

{comment}

🔗 {paper.arxiv_url}"""
        
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
            
            pool_age_info = ""
            if status['pool_age_stats']:
                stats = status['pool_age_stats']
                pool_age_info = f"\n**Pool Age**: {stats['min_age_days']}-{stats['max_age_days']} days (avg: {stats['avg_age_days']:.1f})"
            
            response = f"""📊 **ArXiv Auto-Poster Status**

**Enabled**: {status['enabled']}
**Pool**: {status['pool_size']}/{status['max_pool_size']} papers (retained for {status['pool_retention_days']} days){pool_age_info}
**Candidates**: {status['candidates_count']}/{status['max_candidates']} papers ready for posting
**Blacklist**: {status['blacklist_size']} papers filtered out
**Posted**: {status['posted_total']} total papers
**Today**: {status['posts_today']}/{status['max_posts_per_day']} posts
**Min Score Threshold**: {status['minimum_score_threshold']:.1f}
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
    async def arxiv_discover(self, ctx: niobot.Context):
        """Manually trigger arXiv paper discovery with trending filtering. Owner only."""
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
            
            response = f"🔍 Starting manual discovery...\n\n**Before:** {len(auto_poster.pool)} papers in pool, {len(auto_poster.candidates)} candidates"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
            # Refresh Altmetric data for existing pool papers
            await auto_poster.refresh_altmetric_for_pool()
            
            # Discover new papers
            new_papers = await auto_poster.discover_papers()
            
            if new_papers:
                # Add to pool and update candidates
                auto_poster.pool.extend(new_papers)
                auto_poster.pool.sort(key=lambda p: p.priority_score, reverse=True)
                auto_poster.pool = auto_poster.pool[:auto_poster.max_pool_size]
                await auto_poster._update_candidates()
                auto_poster.save_state()
                
                response = f"✅ **Discovery Complete!**\n\n"
                response += f"📊 **Results:**\n"
                response += f"• Found {len(new_papers)} new trending papers\n"
                response += f"• Pool now has {len(auto_poster.pool)}/{auto_poster.max_pool_size} papers\n"
                response += f"• {len(auto_poster.candidates)}/{auto_poster.max_candidates} candidates ready for posting\n"
                response += f"• {len(auto_poster.blacklist)} papers blacklisted\n\n"
                
                if auto_poster.candidates:
                    top_candidate = auto_poster.candidates[0]
                    response += f"🏆 **Top Candidate:**\n{top_candidate.title[:100]}...\n"
                    response += f"Priority: {top_candidate.priority_score:.1f} | Altmetric: {top_candidate.altmetric_score or 0:.1f} | Accessibility: {top_candidate.accessibility}\n\n"
                
                response += f"Use `!arxiv_candidates` to see all candidates or `!arxiv_post` to post the top one."
            else:
                response = f"📭 **No new papers found**\n\n"
                response += f"Pool still has {len(auto_poster.pool)} papers, {len(auto_poster.candidates)} candidates ready."
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error during discovery: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_post(self, ctx: niobot.Context):
        """Manually trigger posting the next paper from candidates. Owner only."""
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
            
            if not auto_poster.candidates:
                response = "📭 No candidates available to post"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            response = f"📤 Posting top candidate..."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
            success = await auto_poster.post_next_paper()
            
            if success:
                response = f"✅ Paper posted successfully! {len(auto_poster.candidates)} candidates remaining."
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
    async def arxiv_pool(self, ctx: niobot.Context):
        """Show papers in the pool and current candidates. Owner only."""
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
            
            # Show candidates first
            candidates = auto_poster.candidates
            if candidates:
                response = f"🎯 **Current Candidates ({len(candidates)}/{auto_poster.max_candidates})**\n\n"
                for i, paper in enumerate(candidates, 1):
                    accessibility_str = f" | Access: {paper.accessibility or 'unknown'}"
                    response += f"**#{i}. {paper.title[:60]}{'...' if len(paper.title) > 60 else ''}**\n"
                    response += f"   Priority: {paper.priority_score:.1f} | Altmetric: {paper.altmetric_score or 0:.1f}{accessibility_str}\n"
                    response += f"   Categories: {', '.join(paper.categories[:2])}\n"
                    response += f"   🔗 {paper.arxiv_url}\n\n"
            else:
                response = "🎯 **No candidates currently available**\n\n"
            
            # Show pool summary
            pool_papers = auto_poster.pool
            if pool_papers:
                response += f"🏊 **Pool Summary ({len(pool_papers)}/{auto_poster.max_pool_size} papers)**\n"
                response += f"Retention: {auto_poster.pool_retention_days} days | Blacklisted: {len(auto_poster.blacklist)} papers\n\n"
                
                # Show top 10 pool papers
                response += "**Top 10 Pool Papers:**\n"
                for i, paper in enumerate(pool_papers[:10], 1):
                    accessibility_str = f" | Access: {paper.accessibility or 'unknown'}"
                    response += f"{i}. {paper.title[:50]}{'...' if len(paper.title) > 50 else ''}\n"
                    response += f"   Priority: {paper.priority_score:.1f} | Altmetric: {paper.altmetric_score or 0:.1f}{accessibility_str}\n\n"
            else:
                response += "🏊 **Pool is empty**"
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error getting pool status: {str(e)}"
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
        !arxiv_config min_score 100 - Set minimum score threshold for posting
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

**Target Channel**: {auto_poster.target_channel}
**Max Posts Per Day**: {auto_poster.max_posts_per_day}
**Posting Interval**: {auto_poster.posting_interval.total_seconds() / 3600:.1f} hours
**Discovery Interval**: {auto_poster.discovery_interval.total_seconds() / 3600:.1f} hours
**Pool Retention**: {auto_poster.pool_retention_days} days
**Max Pool Size**: {auto_poster.max_pool_size} papers
**Max Candidates**: {auto_poster.max_candidates} papers

**Current State**:
- Posted today: {len(auto_poster.posted_today)}/{auto_poster.max_posts_per_day}
- Pool size: {len(auto_poster.pool)}
- Candidates: {len(auto_poster.candidates)}
- Last posting: {auto_poster.last_posting.strftime('%Y-%m-%d %H:%M UTC') if auto_poster.last_posting else 'Never'}"""
                
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
                    
            elif setting == "min_score" and value:
                try:
                    min_score = float(value)
                    if 0 <= min_score <= 1000:
                        auto_poster.minimum_score_threshold = min_score
                        response = f"✅ Minimum score threshold set to: {min_score:.1f}"
                    else:
                        response = "❌ Minimum score must be between 0 and 1000"
                except ValueError:
                    response = "❌ Invalid number for minimum score"
                    
            else:
                response = """❌ Invalid setting. Available settings:
- channel <#channel:server.com>
- max_posts <1-20>
- interval <0.5-24 hours>
- min_score <0-1000>"""
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error configuring auto-poster: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_trending(self, ctx: niobot.Context, days: int = 3):
        """Analyze trending papers with detailed Altmetric statistics. Owner only."""
        try:
            # Import the tracker (lazy import to avoid startup issues)
            try:
                from arxiv_tracker import ArxivAltmetricTracker
            except ImportError:
                response = "❌ ArXiv tracker not available. Missing dependencies or module not installed."
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            days = max(1, min(days, 14))  # Limit to 1-14 days
            
            response = f"🔍 Analyzing trending papers from the last {days} days with Altmetric data..."
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
            # Initialize tracker and fetch papers
            async with ArxivAltmetricTracker() as tracker:
                papers = await tracker.get_trending_papers(
                    days_back=days,
                    count=20,  # Get more papers for analysis
                    include_altmetric=True
                )
            
            if not papers:
                response = "❌ No AI papers found in the specified time range."
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            # Analyze Altmetric coverage and scores
            papers_with_altmetric = [p for p in papers if p.altmetric_score and p.altmetric_score > 0]
            papers_without_altmetric = [p for p in papers if not p.altmetric_score or p.altmetric_score == 0]
            
            if papers_with_altmetric:
                avg_altmetric = sum(p.altmetric_score for p in papers_with_altmetric if p.altmetric_score) / len(papers_with_altmetric)
                max_altmetric = max(p.altmetric_score for p in papers_with_altmetric if p.altmetric_score)
                top_altmetric_paper = max(papers_with_altmetric, key=lambda p: p.altmetric_score or 0)
            else:
                avg_altmetric = 0
                max_altmetric = 0
                top_altmetric_paper = None
            
            # Generate analysis report
            analysis = f"""📊 **Trending Papers Analysis** (Last {days} days)

**Coverage:**
- Total papers found: {len(papers)}
- Papers with Altmetric data: {len(papers_with_altmetric)} ({len(papers_with_altmetric)/len(papers)*100:.1f}%)
- Papers without Altmetric: {len(papers_without_altmetric)} ({len(papers_without_altmetric)/len(papers)*100:.1f}%)

**Altmetric Statistics:**
- Average score: {avg_altmetric:.1f}
- Highest score: {max_altmetric:.1f}
- Score range: {min(p.altmetric_score or 0 for p in papers):.1f} - {max_altmetric:.1f}"""

            if top_altmetric_paper:
                analysis += f"""

**🏆 Most Trending Paper:**
**{top_altmetric_paper.title[:80]}{'...' if len(top_altmetric_paper.title) > 80 else ''}**
- Altmetric Score: {top_altmetric_paper.altmetric_score:.1f}
- Priority Score: {top_altmetric_paper.priority_score:.1f}
- Authors: {', '.join(top_altmetric_paper.authors[:2])}{'...' if len(top_altmetric_paper.authors) > 2 else ''}
- 🔗 {top_altmetric_paper.arxiv_url}"""

                # Add detailed Altmetric breakdown if available
                if top_altmetric_paper.altmetric_data:
                    data = top_altmetric_paper.altmetric_data
                    mentions = []
                    if data.get('cited_by_tweeters_count', 0) > 0:
                        mentions.append(f"🐦 {data['cited_by_tweeters_count']} tweets")
                    if data.get('cited_by_posts_count', 0) > 0:
                        mentions.append(f"📱 {data['cited_by_posts_count']} posts")
                    if data.get('cited_by_rdts_count', 0) > 0:
                        mentions.append(f"🔴 {data['cited_by_rdts_count']} Reddit")
                    if data.get('cited_by_feeds_count', 0) > 0:
                        mentions.append(f"📰 {data['cited_by_feeds_count']} news")
                    
                    if mentions:
                        analysis += f"\n- Social mentions: {', '.join(mentions)}"

            # Show top 5 papers by priority score
            analysis += f"""

**🔥 Top 5 by Priority Score:**"""
            
            for i, paper in enumerate(papers[:5], 1):
                altmetric_str = f"{paper.altmetric_score:.1f}" if paper.altmetric_score else "0"
                analysis += f"""
{i}. **{paper.title[:50]}{'...' if len(paper.title) > 50 else ''}**
   Priority: {paper.priority_score:.1f} | Altmetric: {altmetric_str}"""

            await ctx.respond(analysis)
            self._log_bot_response(ctx, analysis)
            
        except Exception as e:
            response = f"❌ Error analyzing trending papers: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_criteria(self, ctx: niobot.Context):
        """Show the trending criteria used for filtering papers. Owner only."""
        try:
            auto_poster = getattr(self.bot, 'arxiv_auto_poster', None)
            if not auto_poster:
                response = "❌ ArXiv auto-poster not initialized"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            criteria = """🔥 **Paper Selection Criteria**

Papers go through a multi-stage filtering process:

**🔍 Stage 1: Discovery**
• Papers from last 3 days in AI/ML categories
• Excludes already posted, blacklisted, or pooled papers

**🎯 Stage 2: Trending Criteria**
Papers must meet **at least one** of these criteria:

**🏆 Tier 1 - High Impact:**
• Altmetric score ≥ 5.0 (strong social engagement)

**📱 Tier 2 - Social Engagement:**
• Altmetric score ≥ 2.0 AND has social activity:
  - 3+ tweets, OR
  - 1+ Reddit mentions, OR  
  - 1+ news coverage

**🌟 Tier 3 - Any Social Attention:**
• Any Altmetric score >0 (even minimal social engagement)

**⚡ Tier 4 - Hot & Recent:**
• Priority score ≥ 80.0 (very recent papers in hot AI categories)
• Papers <12 hours old in cs.AI, cs.LG, cs.CL, cs.CV

**🎯 Tier 5 - Quality Fallback (when no Altmetric data available):**
• Recent papers (<24h) in premium categories (cs.AI, cs.LG)
• Quality AI papers with priority score ≥ 60.0

**🛡️ Last Resort:**
• Very recent papers (<6h) in any AI category with priority ≥ 40.0

**🏊 Pool Management:**
• Papers stored for up to 14 days with continuous freshness decay
• Altmetric scores refreshed with tiered frequency (4h → 1d → 3d)

**♿ Stage 3: Candidate Selection & Accessibility**
• Top papers from pool are evaluated for accessibility (LLM assessment)
• Papers with "low" accessibility are blacklisted and removed
• Papers with "high" accessibility get 20% priority bonus
• Only accessible papers become candidates for posting

**📊 Priority Scoring:**
• Exponential Altmetric weighting: (score + 1)²
• Extended freshness decay over 14 days (can go negative)
• Category bonuses for AI/ML fields
• Accessibility multipliers applied after assessment (high: +20%, medium: 0%)"""
            
            await ctx.respond(criteria)
            self._log_bot_response(ctx, criteria)
            
        except Exception as e:
            response = f"❌ Error showing criteria: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_remove_candidate(self, ctx: niobot.Context, arxiv_id: str):
        """Remove a paper from candidates and add to blacklist. Owner only."""
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
            
            # Clean up the arxiv_id (remove any URL parts)
            if '/' in arxiv_id:
                arxiv_id = arxiv_id.split('/')[-1]
            if arxiv_id.startswith('arxiv:'):
                arxiv_id = arxiv_id[6:]
            
            success = auto_poster.remove_candidate(arxiv_id)
            
            if success:
                response = f"✅ Removed candidate {arxiv_id} and added to blacklist"
            else:
                response = f"❌ Paper {arxiv_id} not found in candidates"
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error removing candidate: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_candidates(self, ctx: niobot.Context):
        """Show current candidates with detailed information. Owner only."""
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
            
            candidates = auto_poster.candidates
            if not candidates:
                response = "🎯 **No candidates currently available**\n\nCandidates are automatically selected from the top papers in the pool."
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            response = f"🎯 **Current Candidates ({len(candidates)}/{auto_poster.max_candidates})**\n\n"
            
            for i, paper in enumerate(candidates, 1):
                # Calculate age
                from datetime import datetime, timezone
                age_hours = (datetime.now(timezone.utc) - paper.published).total_seconds() / 3600
                age_str = f"{age_hours:.1f}h" if age_hours < 48 else f"{age_hours/24:.1f}d"
                
                response += f"**#{i}. {paper.title}**\n"
                response += f"📊 Priority: {paper.priority_score:.1f} | Altmetric: {paper.altmetric_score or 0:.1f} | Age: {age_str}\n"
                response += f"♿ Accessibility: {paper.accessibility or 'unknown'}\n"
                response += f"📂 Categories: {', '.join(paper.categories)}\n"
                response += f"👥 Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}\n"
                response += f"🔗 {paper.arxiv_url}\n"
                response += f"🗑️ Remove: `!arxiv_remove_candidate {paper.arxiv_id}`\n\n"
            
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error showing candidates: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_reset_daily(self, ctx: niobot.Context):
        """Reset the daily posting counter. Owner only."""
        try:
            auto_poster = getattr(self.bot, 'arxiv_auto_poster', None)
            if not auto_poster:
                response = "❌ ArXiv auto-poster not initialized"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            old_count = len(auto_poster.posted_today)
            auto_poster.posted_today = []
            auto_poster.save_state()
            
            response = f"✅ Reset daily posting counter (was {old_count}, now 0)"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error resetting daily counter: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response)

    @niobot.command()
    @niobot.is_owner()
    async def arxiv_config_show(self, ctx: niobot.Context):
        """Show current ArXiv auto-poster configuration. Owner only."""
        try:
            auto_poster = getattr(self.bot, 'arxiv_auto_poster', None)
            if not auto_poster:
                response = "❌ ArXiv auto-poster not initialized"
                await ctx.respond(response)
                self._log_bot_response(ctx, response)
                return
            
            response = f"""⚙️ **ArXiv Auto-Poster Configuration**

**Target Channel**: {auto_poster.target_channel}
**Max Posts Per Day**: {auto_poster.max_posts_per_day}
**Posting Interval**: {auto_poster.posting_interval.total_seconds() / 3600:.1f} hours
**Discovery Interval**: {auto_poster.discovery_interval.total_seconds() / 3600:.1f} hours
**Pool Retention**: {auto_poster.pool_retention_days} days
**Max Pool Size**: {auto_poster.max_pool_size} papers
**Max Candidates**: {auto_poster.max_candidates} papers

**Current State**:
- Posted today: {len(auto_poster.posted_today)}/{auto_poster.max_posts_per_day}
- Pool size: {len(auto_poster.pool)}
- Candidates: {len(auto_poster.candidates)}
- Last posting: {auto_poster.last_posting.strftime('%Y-%m-%d %H:%M UTC') if auto_poster.last_posting else 'Never'}"""

            await ctx.respond(response)
            self._log_bot_response(ctx, response)
            
        except Exception as e:
            response = f"❌ Error showing configuration: {str(e)}"
            await ctx.respond(response)
            self._log_bot_response(ctx, response) 