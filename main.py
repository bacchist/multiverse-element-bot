import niobot
import logging
import bot_config
from crawl4ai import AsyncWebCrawler, BrowserConfig
from actions import process_url
from bot_commands import BotCommands
from crawling import set_crawler
from chat_logger import ChatLogger
from autonomous_chat import AutonomousChat
from datetime import datetime, timezone, timedelta
import asyncio

logging.basicConfig(level=logging.INFO, filename="bot.log")

# Initialize chat logger
chat_logger = ChatLogger()

# Store bot startup time to ignore messages from before the bot started
BOT_STARTUP_TIME = datetime.now(timezone.utc)

# Flag to track if we've completed the first sync
INITIAL_SYNC_COMPLETE = False

bot = niobot.NioBot(
    homeserver=bot_config.HOMESERVER,
    user_id=bot_config.USER_ID,
    device_id=bot_config.DEVICE_ID,
    store_path='./store',
    command_prefix="!",
    owner_id=bot_config.OWNER_ID,
    global_message_type="m.text",
    ignore_old_events=True  # Explicitly set this to ignore old events
)

# Initialize autonomous chat
autonomous_chat = AutonomousChat(bot_config.USER_ID, chat_logger)

# Store autonomous_chat on the bot for commands to access
bot.autonomous_chat = autonomous_chat  # type: ignore

browser_config = BrowserConfig()
crawler = AsyncWebCrawler(config=browser_config)
set_crawler(crawler)
bot.crawler = crawler  # Attach crawler to bot for module access  # type: ignore

# Mount the bot commands module
bot.mount_module("bot_commands")

# Optional ArXiv auto-poster integration
try:
    from arxiv_auto_poster import ArxivAutoPoster
    
    # Initialize auto-poster with default settings
    arxiv_auto_poster = ArxivAutoPoster(
        bot=bot,
        target_channel="#ai-papers:themultiverse.school",  # Change this to your desired channel
        max_posts_per_day=999,  # Effectively no limit
        posting_interval=timedelta(hours=4),
        discovery_interval=timedelta(hours=1)
    )
    
    # Attach auto-poster to bot for command access
    setattr(bot, 'arxiv_auto_poster', arxiv_auto_poster)
    
    if arxiv_auto_poster.enabled:
        print("✅ ArXiv auto-poster initialized and enabled")
    else:
        print("⚠️ ArXiv auto-poster initialized but disabled (missing dependencies)")
        
except ImportError as e:
    print(f"ℹ️ ArXiv auto-poster not available: {e}")
    # Set a disabled placeholder so commands can detect it's not available
    setattr(bot, 'arxiv_auto_poster', None)

@bot.on_event("ready")
async def on_ready(_):
    global INITIAL_SYNC_COMPLETE
    print("Bot is ready!")
    print(f"Bot startup time: {BOT_STARTUP_TIME}")
    print(f"Current time: {datetime.now(timezone.utc)}")
    print(f"Ignoring messages from before: {BOT_STARTUP_TIME}")
    
    # Mark that initial sync is complete
    INITIAL_SYNC_COMPLETE = True
    print("Initial sync complete - will now process new messages normally")
    
    # Start the periodic spontaneous message checker
    asyncio.create_task(autonomous_chat.periodic_spontaneous_check(bot))
    
    # Start the arXiv auto-poster background task if available and enabled
    auto_poster = getattr(bot, 'arxiv_auto_poster', None)
    if auto_poster and auto_poster.enabled:
        asyncio.create_task(arxiv_maintenance_task())
        print("🤖 ArXiv auto-poster background task started")

@bot.on_event("command")
async def on_command(ctx):
    # Get command name from context instead of message
    command_name = getattr(ctx, 'command', None)
    if command_name:
        command_name = getattr(command_name, 'name', 'unknown')
    else:
        command_name = 'unknown'
    
    print("User {} ran command {}".format(ctx.message.sender, command_name))
    # Log bot commands
    room_name = getattr(ctx.room, 'display_name', None) or getattr(ctx.room, 'name', None)
    chat_logger.log_bot_action(
        ctx.room.room_id, 
        room_name, 
        f"Command executed: !{command_name} by {ctx.message.sender}"
    )

@bot.on_event("command_error")
async def on_command_error(ctx: niobot.Context, error: Exception):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await ctx.respond(f"[{timestamp}] An error occurred while processing your command. Please try again later.")
    logging.error(f"[{timestamp}] Command error: {error}", exc_info=True)
    # Log command errors
    room_name = getattr(ctx.room, 'display_name', None) or getattr(ctx.room, 'name', None)
    command_name = getattr(getattr(ctx.message, 'command', None), 'name', 'unknown')
    chat_logger.log_bot_action(
        ctx.room.room_id, 
        room_name, 
        f"Command error: !{command_name} by {ctx.message.sender} - {str(error)}"
    )

@bot.on_event("message")
async def on_message(room, message):
    print(f"Observed message from {getattr(message, 'sender', 'unknown')}: {getattr(message, 'body', str(message))}")
    
    # Log all messages to chat logs
    sender = getattr(message, 'sender', 'unknown')
    body = getattr(message, 'body', str(message))
    message_type = getattr(message, 'msgtype', 'm.text')
    room_name = getattr(room, 'display_name', None) or getattr(room, 'name', None)
    
    # Convert server timestamp to datetime if available
    server_timestamp = getattr(message, 'server_timestamp', None)
    timestamp = None
    if server_timestamp:
        timestamp = datetime.fromtimestamp(server_timestamp / 1000, timezone.utc)
    
    # Log the message
    chat_logger.log_message(
        room.room_id,
        room_name,
        sender,
        body,
        message_type,
        timestamp
    )
    
    # Skip processing for stale messages
    message_time = datetime.fromtimestamp(getattr(message, 'server_timestamp', 0) / 1000, timezone.utc)
    now = datetime.now(timezone.utc)
    
    # Enhanced stale message detection
    # 1. Ignore messages from before the bot started
    # 2. During initial sync, be more aggressive about filtering old messages
    # 3. Ignore messages older than 1 hour as a fallback
    # 4. Handle cases where server_timestamp might be missing or invalid
    
    if not getattr(message, 'server_timestamp', None):
        print("Message has no server timestamp; treating as potentially stale.")
        return
    
    # Check if message is from before bot startup
    if message_time < BOT_STARTUP_TIME:
        print(f"Message is from before bot startup ({message_time} < {BOT_STARTUP_TIME}); ignoring as stale.")
        return
    
    # During initial sync, be more conservative about processing messages
    if not INITIAL_SYNC_COMPLETE:
        # During initial sync, only process very recent messages (last 5 minutes)
        if (now - message_time).total_seconds() > 300:  # 5 minutes
            print(f"During initial sync, ignoring message older than 5 minutes ({(now - message_time).total_seconds():.0f}s old)")
            return
        else:
            print(f"During initial sync, processing recent message ({(now - message_time).total_seconds():.0f}s old)")
    
    # General fallback: ignore messages older than 1 hour
    if (now - message_time).total_seconds() > 3600:  # 1 hour fallback
        print(f"Message is older than 1 hour ({(now - message_time).total_seconds():.0f}s); ignoring as stale.")
        return
    
    # Skip processing bot's own messages for autonomous chat
    if sender == bot_config.USER_ID:
        return
    
    # Skip autonomous chat for command messages (messages starting with command prefix)
    if body.startswith(bot.command_prefix):
        print(f"Skipping autonomous chat for command message: {body}")
        return
    
    # Check for autonomous conversation response
    try:
        autonomous_response = await autonomous_chat.handle_message(room, message)
        if autonomous_response:
            print(f"Debug - Autonomous response: {autonomous_response}")
            # Handle both old string format and new dict format for backward compatibility
            if isinstance(autonomous_response, str):
                # Old format - just send as regular message
                print("Debug - Sending as regular message (old format)")
                await bot.send_message(room.room_id, autonomous_response)
            elif isinstance(autonomous_response, dict):
                # New format - check for threading
                response_text = autonomous_response.get('text')
                thread_info = autonomous_response.get('thread_info')
                
                print(f"Debug - Response text: {response_text}")
                print(f"Debug - Thread info: {thread_info}")
                
                if response_text:
                    if thread_info and thread_info.get('event_id'):
                        print(f"Debug - Attempting threaded reply to {thread_info['event_id']}")
                        # Send as threaded reply
                        success = await autonomous_chat._send_threaded_message(
                            bot, room.room_id, response_text, thread_info['event_id']
                        )
                        if not success:
                            print("Debug - Threading failed, sending as regular message")
                            # Fallback to regular message if threading fails
                            await bot.send_message(room.room_id, response_text)
                        else:
                            print("Debug - Threaded message sent successfully")
                    else:
                        print("Debug - No thread info, sending as regular message")
                        # Send as regular message
                        await bot.send_message(room.room_id, response_text)
    except Exception as e:
        print(f"Error in autonomous chat: {e}")
    
    # Continue with existing URL processing logic
    url = next((word for word in body.split() if word.startswith(("http://", "https://"))), None)
    if not url:
        print("No URL found in message; ignoring URL processing.")
        return
    print(f"Processing URL: {url}")
    
    # Log URL processing
    chat_logger.log_bot_action(
        room.room_id,
        room_name,
        f"Processing URL: {url}"
    )
    
    try:
        await process_url(url)
        chat_logger.log_bot_action(
            room.room_id,
            room_name,
            f"Successfully processed URL: {url}"
        )
    except Exception as e:
        print(f"Exception during URL processing: {e}")
        chat_logger.log_bot_action(
            room.room_id,
            room_name,
            f"Failed to process URL {url}: {str(e)}"
        )

# Add event handler for room member events (joins, leaves, etc.)
@bot.on_event("room.member")
async def on_room_member(room, event):
    """Log room membership events like joins, leaves, name changes."""
    sender = getattr(event, 'sender', 'unknown')
    state_key = getattr(event, 'state_key', '')
    content = getattr(event, 'content', {})
    prev_content = getattr(event, 'prev_content', {})
    room_name = getattr(room, 'display_name', None) or getattr(room, 'name', None)
    
    # Convert server timestamp if available
    server_timestamp = getattr(event, 'server_timestamp', None)
    timestamp = None
    if server_timestamp:
        timestamp = datetime.fromtimestamp(server_timestamp / 1000, timezone.utc)
    
    membership = content.get('membership', '')
    prev_membership = prev_content.get('membership', '')
    displayname = content.get('displayname', state_key)
    prev_displayname = prev_content.get('displayname', '')
    
    # Determine what happened
    if prev_membership != membership:
        if membership == 'join':
            if prev_membership == 'invite':
                description = f"accepted invitation and joined the room"
            else:
                description = f"joined the room"
        elif membership == 'leave':
            if sender == state_key:
                description = f"left the room"
            else:
                description = f"was removed from the room by {sender}"
        elif membership == 'invite':
            description = f"was invited to the room by {sender}"
        elif membership == 'ban':
            description = f"was banned from the room by {sender}"
        else:
            description = f"membership changed to {membership}"
    elif displayname != prev_displayname and displayname and prev_displayname:
        description = f"changed display name from '{prev_displayname}' to '{displayname}'"
    elif content.get('avatar_url') != prev_content.get('avatar_url'):
        description = f"changed their avatar"
    else:
        description = f"updated their profile"
    
    chat_logger.log_room_event(
        room.room_id,
        room_name,
        'room.member',
        state_key,
        description,
        timestamp
    )

async def arxiv_maintenance_task():
    """Background task for arXiv auto-poster maintenance."""
    auto_poster = getattr(bot, 'arxiv_auto_poster', None)
    if not auto_poster or not auto_poster.enabled:
        return
        
    logger = logging.getLogger(__name__)
    logger.info("Starting arXiv maintenance task...")
    
    while True:
        try:
            await auto_poster.run_maintenance_cycle()
        except Exception as e:
            logger.error(f"Error in arXiv maintenance cycle: {e}")
        
        # Wait 30 minutes before next check
        await asyncio.sleep(30 * 60)

bot.run(access_token=bot_config.ACCESS_TOKEN)