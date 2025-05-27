import niobot
import logging
import config
from crawl4ai import AsyncWebCrawler, BrowserConfig
from actions import process_url
from bot_commands import BotCommands
from crawling import set_crawler
from chat_logger import ChatLogger
from autonomous_chat import AutonomousChat
from datetime import datetime, timezone
import asyncio

logging.basicConfig(level=logging.INFO, filename="bot.log")

# Initialize chat logger
chat_logger = ChatLogger()

bot = niobot.NioBot(
    homeserver=config.HOMESERVER,
    user_id=config.USER_ID,
    device_id='topdesk',
    store_path='./store',
    command_prefix="!",
    owner_id="@marshall:themultiverse.school"
)

# Initialize autonomous chat
autonomous_chat = AutonomousChat(config.USER_ID, chat_logger)

browser_config = BrowserConfig()
crawler = AsyncWebCrawler(config=browser_config)
set_crawler(crawler)
bot.crawler = crawler  # Attach crawler to bot for module access  # type: ignore

bot.mount_module("bot_commands")

@bot.on_event("ready")
async def on_ready(_):
    print("Bot is ready!")
    # Start the periodic spontaneous message checker
    asyncio.create_task(autonomous_chat.periodic_spontaneous_check(bot))

@bot.on_event("command")
async def on_command(ctx):
    print("User {} ran command {}".format(ctx.message.sender, ctx.message.command.name))
    # Log bot commands
    room_name = getattr(ctx.room, 'display_name', None) or getattr(ctx.room, 'name', None)
    chat_logger.log_bot_action(
        ctx.room.room_id, 
        room_name, 
        f"Command executed: !{ctx.message.command.name} by {ctx.message.sender}"
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
    if (now - message_time).total_seconds() > 3600:
        print("Message is stale; ignoring.")
        return
    
    # Skip processing bot's own messages for autonomous chat
    if sender == config.USER_ID:
        return
    
    # Check for autonomous conversation response
    try:
        autonomous_response = await autonomous_chat.handle_message(room, message)
        if autonomous_response:
            await bot.send_message(room.room_id, autonomous_response)
            chat_logger.log_message(
                room.room_id,
                room_name,
                config.USER_ID,
                autonomous_response,
                "m.text"
            )
            chat_logger.log_bot_action(
                room.room_id,
                room_name,
                f"Autonomous response to {sender}"
            )
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

bot.run(access_token=config.ACCESS_TOKEN)