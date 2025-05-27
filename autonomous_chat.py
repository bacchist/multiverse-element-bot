import asyncio
import random
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path
from baml_client.sync_client import b
from chat_logger import ChatLogger

class AutonomousChat:
    """Handles autonomous conversation capabilities for the bot."""
    
    def __init__(self, bot_user_id: str, chat_logger: ChatLogger):
        self.bot_user_id = bot_user_id
        self.chat_logger = chat_logger
        self.last_response_times: Dict[str, datetime] = {}  # Track when bot last spoke in each room
        self.conversation_history: Dict[str, List[Dict[str, Any]]] = {}  # Recent messages per room
        self.max_history_length = 10  # Keep last 10 messages for context
        self.min_response_interval = timedelta(minutes=2)  # Don't respond too frequently
        self.spontaneous_check_interval = timedelta(minutes=15)  # Check for spontaneous messages
        self.last_spontaneous_check: Dict[str, datetime] = {}
    
    def add_message_to_history(self, room_id: str, sender: str, content: str, timestamp: Optional[datetime] = None):
        """Add a message to the conversation history for a room."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        if room_id not in self.conversation_history:
            self.conversation_history[room_id] = []
        
        message = {
            "sender": sender,
            "content": content,
            "timestamp": timestamp.strftime("%H:%M"),
            "is_bot_message": sender == self.bot_user_id
        }
        
        self.conversation_history[room_id].append(message)
        
        # Keep only recent messages
        if len(self.conversation_history[room_id]) > self.max_history_length:
            self.conversation_history[room_id] = self.conversation_history[room_id][-self.max_history_length:]
    
    def _can_respond_now(self, room_id: str) -> bool:
        """Check if enough time has passed since the bot's last response in this room."""
        if room_id not in self.last_response_times:
            return True
        
        time_since_last = datetime.now(timezone.utc) - self.last_response_times[room_id]
        return time_since_last >= self.min_response_interval
    
    def _should_check_spontaneous(self, room_id: str) -> bool:
        """Check if it's time to consider a spontaneous message."""
        if room_id not in self.last_spontaneous_check:
            self.last_spontaneous_check[room_id] = datetime.now(timezone.utc)
            return False
        
        time_since_check = datetime.now(timezone.utc) - self.last_spontaneous_check[room_id]
        return time_since_check >= self.spontaneous_check_interval
    
    def _get_conversation_context(self, room_id: str, room_name: Optional[str] = None):
        """Build conversation context for BAML functions."""
        recent_messages = self.conversation_history.get(room_id, [])
        
        # Convert to BAML Message format
        baml_messages = []
        for msg in recent_messages:
            baml_messages.append(b.Message(
                sender=msg["sender"],
                content=msg["content"],
                timestamp=msg["timestamp"],
                is_bot_message=msg["is_bot_message"]
            ))
        
        return b.ConversationContext(
            room_name=room_name,
            recent_messages=baml_messages,
            bot_user_id=self.bot_user_id
        )
    
    async def should_respond_to_message(self, room_id: str, room_name: Optional[str], 
                                      sender: str, content: str, 
                                      timestamp: Optional[datetime] = None) -> bool:
        """Determine if the bot should respond to a specific message."""
        # Don't respond to own messages
        if sender == self.bot_user_id:
            return False
        
        # Check rate limiting
        if not self._can_respond_now(room_id):
            return False
        
        # Add message to history
        self.add_message_to_history(room_id, sender, content, timestamp)
        
        try:
            # Get conversation context
            context = self._get_conversation_context(room_id, room_name)
            
            # Create the new message
            new_message = b.Message(
                sender=sender,
                content=content,
                timestamp=timestamp.strftime("%H:%M") if timestamp else datetime.now().strftime("%H:%M"),
                is_bot_message=False
            )
            
            # Ask AI if we should respond
            decision = await asyncio.to_thread(b.ShouldRespondToConversation, context, new_message)
            
            print(f"Response decision for '{content[:50]}...': {decision.should_respond} (confidence: {decision.confidence:.2f}) - {decision.reasoning}")
            
            return decision.should_respond and decision.confidence > 0.6
            
        except Exception as e:
            print(f"Error in should_respond_to_message: {e}")
            return False
    
    async def generate_response(self, room_id: str, room_name: Optional[str], 
                              sender: str, content: str, 
                              timestamp: Optional[datetime] = None) -> Optional[str]:
        """Generate a conversational response to a message."""
        try:
            # Get conversation context
            context = self._get_conversation_context(room_id, room_name)
            
            # Create the new message
            new_message = b.Message(
                sender=sender,
                content=content,
                timestamp=timestamp.strftime("%H:%M") if timestamp else datetime.now().strftime("%H:%M"),
                is_bot_message=False
            )
            
            # Generate response
            response = await asyncio.to_thread(b.GenerateChatResponse, context, new_message)
            
            # Update last response time
            self.last_response_times[room_id] = datetime.now(timezone.utc)
            
            # Add bot's response to history
            self.add_message_to_history(room_id, self.bot_user_id, response.message)
            
            print(f"Generated response (tone: {response.tone}): {response.message}")
            
            return response.message
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return None
    
    async def check_spontaneous_message(self, room_id: str, room_name: Optional[str]) -> Optional[str]:
        """Check if the bot wants to send a spontaneous message."""
        # Check if it's time to consider spontaneous messages
        if not self._should_check_spontaneous(room_id):
            return None
        
        # Update check time
        self.last_spontaneous_check[room_id] = datetime.now(timezone.utc)
        
        # Don't send spontaneous messages too soon after last response
        if not self._can_respond_now(room_id):
            return None
        
        try:
            # Get conversation context
            context = self._get_conversation_context(room_id, room_name)
            
            # Check if bot wants to say something
            spontaneous = await asyncio.to_thread(b.GenerateSpontaneousMessage, context)
            
            if spontaneous.should_send and spontaneous.message:
                # Update last response time
                self.last_response_times[room_id] = datetime.now(timezone.utc)
                
                # Add bot's message to history
                self.add_message_to_history(room_id, self.bot_user_id, spontaneous.message)
                
                print(f"Spontaneous message: {spontaneous.message} (reasoning: {spontaneous.reasoning})")
                
                return spontaneous.message
            
            return None
            
        except Exception as e:
            print(f"Error checking spontaneous message: {e}")
            return None
    
    async def handle_message(self, room, message) -> Optional[str]:
        """Main handler for incoming messages. Returns response if bot should respond."""
        sender = getattr(message, 'sender', 'unknown')
        content = getattr(message, 'body', '')
        room_name = getattr(room, 'display_name', None) or getattr(room, 'name', None)
        
        # Get timestamp
        server_timestamp = getattr(message, 'server_timestamp', None)
        timestamp = None
        if server_timestamp:
            timestamp = datetime.fromtimestamp(server_timestamp / 1000, timezone.utc)
        
        # Check if we should respond
        should_respond = await self.should_respond_to_message(
            room.room_id, room_name, sender, content, timestamp
        )
        
        if should_respond:
            return await self.generate_response(
                room.room_id, room_name, sender, content, timestamp
            )
        
        # Even if we don't respond to this message, add it to history
        if sender != self.bot_user_id:
            self.add_message_to_history(room.room_id, sender, content, timestamp)
        
        return None
    
    async def periodic_spontaneous_check(self, bot):
        """Periodic task to check for spontaneous messages in all rooms."""
        while True:
            try:
                # Wait for the check interval
                await asyncio.sleep(self.spontaneous_check_interval.total_seconds())
                
                # Check each room the bot is in
                for room_id, room in bot.rooms.items():
                    room_name = getattr(room, 'display_name', None) or getattr(room, 'name', None)
                    
                    # Random chance to check (don't check every room every time)
                    if random.random() < 0.3:  # 30% chance per room per check
                        message = await self.check_spontaneous_message(room_id, room_name)
                        
                        if message:
                            # Send the spontaneous message
                            await bot.send_message(room_id, message)
                            
                            # Log the message
                            self.chat_logger.log_message(
                                room_id, room_name, self.bot_user_id, message, "m.text"
                            )
                            
                            # Small delay between rooms to avoid spam
                            await asyncio.sleep(5)
                
            except Exception as e:
                print(f"Error in periodic spontaneous check: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying 