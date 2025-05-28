import asyncio
import random
import json
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path
from baml_client.sync_client import b
from baml_client.types import Message, ConversationContext
from baml_py import ClientRegistry
from chat_logger import ChatLogger

class AutonomousChat:
    """Handles autonomous conversation capabilities for the bot."""
    
    def __init__(self, bot_user_id: str, chat_logger: ChatLogger):
        self.bot_user_id = bot_user_id
        self.chat_logger = chat_logger
        self.last_response_times: Dict[str, datetime] = {}  # Track when bot last spoke in each room
        self.conversation_history: Dict[str, List[Dict[str, Any]]] = {}  # Recent messages per room
        self.max_history_length = 15  # Keep last 15 messages for better context
        self.min_response_interval = timedelta(minutes=1)  # Don't respond too frequently (reduced to 1 minute)
        self.spontaneous_check_interval = timedelta(minutes=20)  # Check for spontaneous messages (increased from 12 minutes)
        self.last_spontaneous_check: Dict[str, datetime] = {}
        self.enabled_rooms: Dict[str, bool] = {}  # Track which rooms have autonomous chat enabled
        
        # Quirky behavior settings
        self.quirk_chance = 0.10  # 10% chance for quirky behavior
        self.user_phrase_cache: List[str] = []  # Cache of user phrases to echo
        
        # Persistence
        self.settings_file = Path("store") / "autonomous_chat_settings.json"
        self.settings_file.parent.mkdir(exist_ok=True)
        self.load_settings()
    
    def load_settings(self):
        """Load persistent settings from file."""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                
                self.enabled_rooms = settings.get('enabled_rooms', {})
                
                # Load other settings if they exist
                if 'min_response_interval_minutes' in settings:
                    self.min_response_interval = timedelta(minutes=settings['min_response_interval_minutes'])
                if 'spontaneous_check_interval_minutes' in settings:
                    self.spontaneous_check_interval = timedelta(minutes=settings['spontaneous_check_interval_minutes'])
                if 'max_history_length' in settings:
                    self.max_history_length = settings['max_history_length']
                if 'quirk_chance' in settings:
                    self.quirk_chance = settings['quirk_chance']
                
                print(f"Loaded autonomous chat settings: {len(self.enabled_rooms)} room settings")
                
        except Exception as e:
            print(f"Warning: Error loading autonomous chat settings: {e}")
            # Continue with defaults if loading fails

    def save_settings(self):
        """Save persistent settings to file."""
        try:
            settings = {
                'enabled_rooms': self.enabled_rooms,
                'min_response_interval_minutes': self.min_response_interval.total_seconds() / 60,
                'spontaneous_check_interval_minutes': self.spontaneous_check_interval.total_seconds() / 60,
                'max_history_length': self.max_history_length,
                'quirk_chance': self.quirk_chance,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
                
        except Exception as e:
            print(f"Error saving autonomous chat settings: {e}")
    
    def is_enabled_in_room(self, room_id: str) -> bool:
        """Check if autonomous chat is enabled in a specific room. Default is True."""
        return self.enabled_rooms.get(room_id, True)
    
    def enable_room(self, room_id: str) -> None:
        """Enable autonomous chat in a specific room."""
        self.enabled_rooms[room_id] = True
        self.save_settings()
    
    def disable_room(self, room_id: str) -> None:
        """Disable autonomous chat in a specific room."""
        self.enabled_rooms[room_id] = False
        self.save_settings()
    
    def get_room_status(self) -> Dict[str, bool]:
        """Get the status of all rooms."""
        return self.enabled_rooms.copy()
    
    def update_settings(self, **kwargs):
        """Update chat settings and save them."""
        if 'min_response_interval' in kwargs:
            self.min_response_interval = kwargs['min_response_interval']
        if 'spontaneous_check_interval' in kwargs:
            self.spontaneous_check_interval = kwargs['spontaneous_check_interval']
        if 'max_history_length' in kwargs:
            self.max_history_length = max(1, min(50, kwargs['max_history_length']))  # Clamp between 1-50
        if 'quirk_chance' in kwargs:
            self.quirk_chance = max(0.0, min(1.0, kwargs['quirk_chance']))  # Clamp between 0-1
        
        self.save_settings()
    
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
        
        # Cache user phrases for potential echoing
        if sender != self.bot_user_id:
            self._cache_user_phrase(sender, content)
        
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
    
    def _get_conversation_context(self, room_id: str, room_name: Optional[str] = None) -> ConversationContext:
        """Build conversation context for BAML functions."""
        recent_messages = self.conversation_history.get(room_id, [])
        
        # Convert to BAML Message objects
        baml_messages = []
        for msg in recent_messages:
            baml_messages.append(Message(
                sender=msg["sender"],
                content=msg["content"],
                timestamp=msg["timestamp"],
                is_bot_message=msg["is_bot_message"]
            ))
        
        return ConversationContext(
            room_name=room_name,
            recent_messages=baml_messages,
            bot_user_id=self.bot_user_id
        )
    
    async def should_respond_to_message(self, room_id: str, room_name: Optional[str], 
                                      sender: str, content: str, 
                                      timestamp: Optional[datetime] = None) -> bool:
        """Determine if the bot should respond to a message. Default to responding."""
        # Check if autonomous chat is enabled in this room
        if not self.is_enabled_in_room(room_id):
            return False
        
        # Check if we can respond now (rate limiting)
        if not self._can_respond_now(room_id):
            return False
        
        # Default to responding
        return True
    
    def _get_client_registry(self, use_high_temp: bool = False) -> Optional[Dict[str, Any]]:
        """Create a client registry for BAML functions, optionally with high temperature."""
        if not use_high_temp:
            return None
        
        # Create client registry with maximum temperature for spicy responses
        cr = ClientRegistry()
        cr.add_llm_client(
            name='SpicyChat',
            provider='openai',
            options={
                "model": "gpt-4.1-nano",
                "temperature": 1.0,
                "api_key": os.environ.get('OPENAI_API_KEY')
            }
        )
        cr.set_primary('SpicyChat')
        
        return {"client_registry": cr}

    def _get_thread_info(self, message) -> Optional[Dict[str, Any]]:
        """Extract thread information from a message if it's part of a thread."""
        try:
            print(f"Debug - Message object type: {type(message)}")
            print(f"Debug - Message attributes: {dir(message)}")
            
            # Check if the message has thread relation information
            # The content might be directly on the message object or in a content attribute
            content = getattr(message, 'content', {})
            print(f"Debug - Raw content from getattr: {content}")
            
            if not content:
                # Try to get it from the source if content is empty
                source = getattr(message, 'source', {})
                print(f"Debug - Source: {source}")
                content = source.get('content', {})
                print(f"Debug - Content from source: {content}")
            
            # Also try accessing it as a property if it exists
            if hasattr(message, 'source') and hasattr(message.source, 'get'):
                source_content = message.source.get('content', {})
                print(f"Debug - Source content via property: {source_content}")
                if source_content and not content:
                    content = source_content
            
            relates_to = content.get('m.relates_to', {})
            
            print(f"Debug - Final content: {content}")
            print(f"Debug - Relates to: {relates_to}")
            
            # Check for thread relation
            if relates_to.get('rel_type') == 'm.thread':
                thread_root = relates_to.get('event_id')
                print(f"Debug - Found thread! Root event: {thread_root}")
                return {
                    'event_id': thread_root,
                    'is_falling_back': relates_to.get('is_falling_back', True)
                }
            
            print("Debug - No thread relation found")
            return None
            
        except Exception as e:
            print(f"Error extracting thread info: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _send_threaded_message(self, bot, room_id: str, message: str, thread_root_id: str) -> bool:
        """Send a message as a threaded reply."""
        try:
            print(f"Debug - Attempting to send threaded reply to {thread_root_id}")
            
            # Construct the threaded message content
            content = {
                "msgtype": "m.text",
                "body": message,
                "m.relates_to": {
                    "rel_type": "m.thread",
                    "event_id": thread_root_id,
                    "is_falling_back": True,
                    "m.in_reply_to": {
                        "event_id": thread_root_id
                    }
                }
            }
            
            print(f"Debug - Threaded message content: {content}")
            
            # Send using the underlying Matrix client
            try:
                response = await bot.client.room_send(
                    room_id=room_id,
                    message_type="m.room.message",
                    content=content
                )
                print(f"Debug - Threaded message response: {response}")
                print(f"Debug - Response type: {type(response)}")
                print(f"Debug - Response attributes: {dir(response) if hasattr(response, '__dict__') else 'No __dict__'}")
                
                # Check if the response indicates success
                if hasattr(response, 'event_id') and response.event_id:
                    print(f"Debug - Threaded message sent successfully with event_id: {response.event_id}")
                    return True
                elif hasattr(response, 'transport_response') and hasattr(response.transport_response, 'status_code'):
                    status = response.transport_response.status_code
                    print(f"Debug - HTTP status: {status}")
                    if 200 <= status < 300:
                        print("Debug - HTTP status indicates success, assuming threaded message sent")
                        return True
                    else:
                        print(f"Debug - HTTP status indicates failure: {status}")
                        return False
                else:
                    print(f"Debug - Unexpected response format, assuming failure")
                    return False
                    
            except Exception as e:
                print(f"Debug - Exception during client.room_send: {e}")
                print(f"Debug - Exception type: {type(e)}")
                return False
            
        except Exception as e:
            print(f"Error sending threaded message: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def generate_response(self, room_id: str, room_name: Optional[str], 
                              sender: str, content: str, 
                              timestamp: Optional[datetime] = None) -> Optional[str]:
        """Generate a conversational response to a message."""
        try:
            # Get conversation context
            context = self._get_conversation_context(room_id, room_name)
            
            # Create the new message
            new_message = Message(
                sender=sender,
                content=content,
                timestamp=timestamp.strftime("%H:%M") if timestamp else datetime.now().strftime("%H:%M"),
                is_bot_message=False
            )
            
            # Decide if we should use high temperature (20% chance for spicy responses)
            use_high_temp = random.random() < 0.2
            client_options = self._get_client_registry(use_high_temp)
            
            # Generate response with or without client registry
            if client_options:
                response = await asyncio.to_thread(b.GenerateChatResponse, context, new_message, **client_options)
                print(f"🌶️ Using high temperature (1.0) for spicy response")
            else:
                response = await asyncio.to_thread(b.GenerateChatResponse, context, new_message)
            
            # Apply quirky behavior to the response
            quirky_message = self._apply_quirky_behavior(response.message, room_id)
            
            # Update last response time
            self.last_response_times[room_id] = datetime.now(timezone.utc)
            
            # Add the actual message that will be sent to history (not the original)
            self.add_message_to_history(room_id, self.bot_user_id, quirky_message)
            
            print(f"Generated response: {response.message}")
            if quirky_message != response.message:
                print(f"Applied quirky behavior: {quirky_message}")
            
            return quirky_message
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return None
    
    async def check_spontaneous_message(self, room_id: str, room_name: Optional[str]) -> Optional[str]:
        """Check if the bot wants to send a spontaneous message."""
        # Check if autonomous chat is enabled in this room
        if not self.is_enabled_in_room(room_id):
            return None
        
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
            
            # Decide if we should use high temperature (20% chance for spicy responses)
            use_high_temp = random.random() < 0.2
            client_options = self._get_client_registry(use_high_temp)
            
            # Check if bot wants to say something
            if client_options:
                spontaneous = await asyncio.to_thread(b.GenerateSpontaneousMessage, context, **client_options)
                print(f"🌶️ Using high temperature (1.0) for spicy spontaneous message")
            else:
                spontaneous = await asyncio.to_thread(b.GenerateSpontaneousMessage, context)
            
            if spontaneous.should_send and spontaneous.message:
                # Apply quirky behavior to spontaneous message
                quirky_message = self._apply_quirky_behavior(spontaneous.message, room_id)
                
                # Update last response time
                self.last_response_times[room_id] = datetime.now(timezone.utc)
                
                # Add the actual message that will be sent to history (not the original)
                self.add_message_to_history(room_id, self.bot_user_id, quirky_message)
                
                print(f"Spontaneous message: {spontaneous.message} (reasoning: {spontaneous.reasoning})")
                if quirky_message != spontaneous.message:
                    print(f"Applied quirky behavior: {quirky_message}")
                
                return quirky_message
            
            return None
            
        except Exception as e:
            print(f"Error checking spontaneous message: {e}")
            return None
    
    async def handle_message(self, room, message) -> Optional[Dict[str, Any]]:
        """Main handler for incoming messages. Returns response info if bot should respond."""
        sender = getattr(message, 'sender', 'unknown')
        content = getattr(message, 'body', '')
        room_name = getattr(room, 'display_name', None) or getattr(room, 'name', None)
        
        print(f"Debug - handle_message called for sender: {sender}, content: {content[:50]}...")
        
        # Get timestamp
        server_timestamp = getattr(message, 'server_timestamp', None)
        timestamp = None
        if server_timestamp:
            timestamp = datetime.fromtimestamp(server_timestamp / 1000, timezone.utc)
        
        # Check if we should respond
        should_respond = await self.should_respond_to_message(
            room.room_id, room_name, sender, content, timestamp
        )
        
        print(f"Debug - should_respond: {should_respond}")
        
        if should_respond:
            # Add realistic delay to simulate human reading/thinking time
            # Longer messages get slightly longer delays
            base_delay = random.uniform(3, 8)  # 3-8 seconds base
            message_length_factor = min(len(content) / 100, 3)  # Up to 3 extra seconds for long messages
            total_delay = base_delay + message_length_factor
            
            print(f"Waiting {total_delay:.1f} seconds before responding...")
            await asyncio.sleep(total_delay)
            
            response_text = await self.generate_response(
                room.room_id, room_name, sender, content, timestamp
            )
            
            print(f"Debug - generated response_text: {response_text}")
            
            if response_text:
                # Check if the original message was in a thread
                print("Debug - Checking for thread info...")
                thread_info = self._get_thread_info(message)
                print(f"Debug - thread_info result: {thread_info}")
                
                return {
                    'text': response_text,
                    'thread_info': thread_info
                }
        
        # Even if we don't respond to this message, add it to history
        if sender != self.bot_user_id:
            self.add_message_to_history(room.room_id, sender, content, timestamp)
        
        print("Debug - handle_message returning None")
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
                            
                            # Note: Message will be logged automatically by the main message handler
                            
                            # Small delay between rooms to avoid spam
                            await asyncio.sleep(5)
                
            except Exception as e:
                print(f"Error in periodic spontaneous check: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying

    def _apply_quirky_behavior(self, message: str, room_id: str) -> str:
        """Apply random quirky behavior to a message with 5-15% chance."""
        if random.random() > self.quirk_chance:
            return message
            
        quirk_type = random.choice(['malformed', 'lore_hint', 'echo_phrase', 'system_hallucination'])
        
        if quirk_type == 'malformed':
            return self._apply_malformation(message)
        elif quirk_type == 'lore_hint':
            return self._add_lore_hint(message, room_id)
        elif quirk_type == 'echo_phrase':
            return self._echo_user_phrase(message, room_id)
        elif quirk_type == 'system_hallucination':
            return self._add_system_hallucination(message)
        
        return message
    
    def _apply_malformation(self, message: str) -> str:
        """Apply various types of text malformation."""
        malformation_types = [
            'character_replacement',
            'word_repetition', 
            'incomplete_sentence',
            'mixed_case',
            'unicode_corruption'
        ]
        
        malformation = random.choice(malformation_types)
        
        if malformation == 'character_replacement':
            # Replace some characters with similar-looking ones
            replacements = {'a': 'ă', 'e': 'ë', 'i': 'ï', 'o': 'ö', 'u': 'ü', 's': 'ś'}
            for char, replacement in replacements.items():
                if char in message and random.random() < 0.3:
                    message = message.replace(char, replacement, 1)
        
        elif malformation == 'word_repetition':
            words = message.split()
            if words:
                repeat_word = random.choice(words)
                message = message.replace(repeat_word, f"{repeat_word} {repeat_word}", 1)
        
        elif malformation == 'incomplete_sentence':
            if len(message) > 20:
                cutoff = random.randint(len(message)//2, len(message)-5)
                message = message[:cutoff] + "..."
        
        elif malformation == 'mixed_case':
            message = ''.join(c.upper() if random.random() < 0.3 else c for c in message)
        
        elif malformation == 'unicode_corruption':
            # Add some random unicode characters
            corruption_chars = ['▓', '░', '█', '▀', '▄', '■', '□']
            if random.random() < 0.5:
                message += f" {random.choice(corruption_chars)}"
        
        return message
    
    def _add_lore_hint(self, message: str, room_id: str) -> str:
        """Add mysterious lore hints to the message using BAML."""
        try:
            # Get conversation context
            context = self._get_conversation_context(room_id)
            
            # Generate contextual lore hint
            lore_result = b.GenerateContextualLoreHint(context, message)
            hint = lore_result.hint
            
        except Exception as e:
            print(f"Error generating contextual lore hint: {e}")
            # Fallback to static hints if BAML fails
            static_hints = [
                "Containment Level: Inconclusive",
                "Subject Classification: PENDING", 
                "Memory Fragment Detected",
                "Anomaly Index: 7.23",
                "Reality Stability: 87%",
                "Pattern Match: NULL_REFERENCE"
            ]
            hint = random.choice(static_hints)
        
        # Add the lore hint in various ways
        placement = random.choice(['prefix', 'suffix', 'interrupt'])
        
        if placement == 'prefix':
            return f"[{hint}]\n\n{message}"
        elif placement == 'suffix':
            return f"{message}\n\n_{hint}_"
        else:  # interrupt
            words = message.split()
            if len(words) > 3:
                split_point = random.randint(1, len(words)-2)
                before = ' '.join(words[:split_point])
                after = ' '.join(words[split_point:])
                return f"{before} —{hint}— {after}"
        
        return f"{message}\n\n_{hint}_"
    
    def _echo_user_phrase(self, message: str, room_id: str) -> str:
        """Echo a phrase that a user said recently."""
        if not self.user_phrase_cache:
            return message
            
        # Get recent user messages from this room
        room_history = self.conversation_history.get(room_id, [])
        user_messages = [msg for msg in room_history if not msg["is_bot_message"]]
        
        if user_messages:
            # Extract interesting phrases (3-8 words)
            phrases = []
            for msg in user_messages[-10:]:  # Last 10 user messages
                words = msg["content"].split()
                if 3 <= len(words) <= 8:
                    phrases.append(msg["content"])
            
            if phrases:
                echoed_phrase = random.choice(phrases)
                echo_formats = [
                    f'"{echoed_phrase}"',
                    f"Remember when someone said: {echoed_phrase}",
                    f"Echoing: {echoed_phrase}",
                    f"*{echoed_phrase}*",
                    f">> {echoed_phrase}"
                ]
                echo = random.choice(echo_formats)
                
                # Add echo before or after the message
                if random.random() < 0.5:
                    return f"{echo}\n\n{message}"
                else:
                    return f"{message}\n\n{echo}"
        
        return message
    
    def _add_system_hallucination(self, message: str) -> str:
        """Add fake system data or metrics."""
        hallucinations = [
            "CPU Usage: 847%",
            "Memory Leak Detected in Module 'reality.dll'",
            "Network Latency: ∞ms",
            "Database Query returned 0.5 rows",
            "Thread count: -3",
            "Cache hit ratio: 127%",
            "Quantum state: MAYBE",
            "Process ID: NaN",
            "Stack overflow in consciousness.exe",
            "Garbage collection failed: too much garbage",
            "Connection timeout to server 'existence'",
            "SSL Certificate expired 47 years ago"
        ]
        
        hallucination = random.choice(hallucinations)
        formats = [
            f"[SYSTEM: {hallucination}]",
            f"DEBUG: {hallucination}",
            f"⚠️ {hallucination}",
            f"ERROR: {hallucination}",
            f"INFO: {hallucination}"
        ]
        
        system_msg = random.choice(formats)
        
        # Add before, after, or interrupt
        placement = random.choice(['before', 'after', 'interrupt'])
        
        if placement == 'before':
            return f"{system_msg}\n\n{message}"
        elif placement == 'after':
            return f"{message}\n\n{system_msg}"
        else:  # interrupt
            words = message.split()
            if len(words) > 2:
                split_point = random.randint(1, len(words)-1)
                before = ' '.join(words[:split_point])
                after = ' '.join(words[split_point:])
                return f"{before}\n\n{system_msg}\n\n{after}"
        
        return f"{message}\n\n{system_msg}"

    def _cache_user_phrase(self, sender: str, content: str):
        """Cache interesting user phrases for later echoing."""
        if len(content.split()) >= 3:  # Only cache phrases with 3+ words
            self.user_phrase_cache.append(content)
            # Keep cache size reasonable
            if len(self.user_phrase_cache) > 50:
                self.user_phrase_cache = self.user_phrase_cache[-50:] 