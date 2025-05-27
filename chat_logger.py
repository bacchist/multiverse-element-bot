import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

class ChatLogger:
    """Handles logging of chat messages to separate files organized by room."""
    
    def __init__(self, log_directory: str = "chat_logs"):
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(exist_ok=True)
        self.loggers = {}  # Cache for room-specific loggers
    
    def _get_safe_room_name(self, room_id: str, room_name: Optional[str] = None) -> str:
        """Convert room ID/name to a safe filename."""
        if room_name:
            # Use room name if available, sanitize for filename
            safe_name = "".join(c for c in room_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_name = safe_name.replace(' ', '_')
            return f"{safe_name}_{room_id.replace(':', '_').replace('!', '').replace('#', '')}"
        else:
            # Fallback to room ID only
            return room_id.replace(':', '_').replace('!', '').replace('#', '')
    
    def _get_room_logger(self, room_id: str, room_name: Optional[str] = None) -> logging.Logger:
        """Get or create a logger for a specific room."""
        if room_id not in self.loggers:
            safe_room_name = self._get_safe_room_name(room_id, room_name)
            log_file = self.log_directory / f"{safe_room_name}.log"
            
            # Create logger
            logger = logging.getLogger(f"chat.{room_id}")
            logger.setLevel(logging.INFO)
            
            # Remove existing handlers to avoid duplicates
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
            
            # Create file handler
            handler = logging.FileHandler(log_file, encoding='utf-8')
            formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
            # Prevent propagation to root logger
            logger.propagate = False
            
            self.loggers[room_id] = logger
            
        return self.loggers[room_id]
    
    def log_message(self, room_id: str, room_name: Optional[str], sender: str, message_body: str, 
                   message_type: str = "m.text", timestamp: Optional[datetime] = None):
        """Log a chat message to the appropriate room log file."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        logger = self._get_room_logger(room_id, room_name)
        
        # Format the log entry
        if message_type == "m.text":
            log_entry = f"[{sender}] {message_body}"
        elif message_type == "m.emote":
            log_entry = f"* {sender} {message_body}"
        elif message_type == "m.notice":
            log_entry = f"[NOTICE] [{sender}] {message_body}"
        elif message_type == "m.image":
            log_entry = f"[{sender}] [IMAGE] {message_body}"
        elif message_type == "m.file":
            log_entry = f"[{sender}] [FILE] {message_body}"
        elif message_type == "m.audio":
            log_entry = f"[{sender}] [AUDIO] {message_body}"
        elif message_type == "m.video":
            log_entry = f"[{sender}] [VIDEO] {message_body}"
        else:
            log_entry = f"[{sender}] [{message_type}] {message_body}"
        
        logger.info(log_entry)
    
    def log_room_event(self, room_id: str, room_name: Optional[str], event_type: str, 
                      sender: str, description: str, timestamp: Optional[datetime] = None):
        """Log a room event (joins, leaves, name changes, etc.)."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        logger = self._get_room_logger(room_id, room_name)
        log_entry = f"[SYSTEM] {sender} {description}"
        logger.info(log_entry)
    
    def log_bot_action(self, room_id: str, room_name: Optional[str], action: str, 
                      timestamp: Optional[datetime] = None):
        """Log bot actions in the room."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        logger = self._get_room_logger(room_id, room_name)
        log_entry = f"[BOT] {action}"
        logger.info(log_entry) 