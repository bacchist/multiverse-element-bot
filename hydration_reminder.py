import json
import os
import logging
from datetime import datetime, timezone
from baml_client import b

logger = logging.getLogger(__name__)

class HydrationReminderHandler:
    def __init__(self, counter_file_path: str = "store/hydration_counter.json"):
        self.counter_file_path = counter_file_path
        self.target_room_id = "#neurospicy:themultiverse.school"
        self.reminder_user_id = "@reminder:themultiverse.school"
        self.target_message = "@room Don't forget to drink water!"
        self._counter: int = 0
        self._load_counter()
    
    def _load_counter(self):
        """Load the counter from persistent storage."""
        try:
            if os.path.exists(self.counter_file_path):
                with open(self.counter_file_path, 'r') as f:
                    data = json.load(f)
                    self._counter = int(data.get('count', 0))
                    logger.info(f"Loaded hydration reminder counter: {self._counter}")
            else:
                self._counter = 0
                logger.info("No existing counter file found, starting from 0")
        except Exception as e:
            logger.error(f"Error loading counter: {e}")
            self._counter = 0
    
    def _save_counter(self):
        """Save the counter to persistent storage."""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.counter_file_path), exist_ok=True)
            
            data = {
                'count': self._counter,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            
            with open(self.counter_file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved hydration reminder counter: {self._counter}")
        except Exception as e:
            logger.error(f"Error saving counter: {e}")
    
    def should_handle_message(self, room_id: str, sender: str, message_body: str) -> bool:
        """Check if this message should trigger the hydration reminder response."""
        logger.debug(f"HYDRATION HANDLER: Checking message - room_id='{room_id}', sender='{sender}', body='{message_body}'")
        logger.debug(f"HYDRATION HANDLER: Target room='{self.target_room_id}', target sender='{self.reminder_user_id}', target message='{self.target_message}'")
        
        # Check if it's the right room
        if room_id != self.target_room_id:
            logger.debug(f"HYDRATION HANDLER: Room mismatch - got '{room_id}', expected '{self.target_room_id}'")
            return False
        
        # Check if it's from the reminder bot
        if sender != self.reminder_user_id:
            logger.debug(f"HYDRATION HANDLER: Sender mismatch - got '{sender}', expected '{self.reminder_user_id}'")
            return False
        
        # Check if it's the exact message we're looking for
        if message_body.strip() != self.target_message:
            logger.debug(f"HYDRATION HANDLER: Message mismatch - got '{message_body.strip()}', expected '{self.target_message}'")
            return False
        
        logger.debug("HYDRATION HANDLER: All checks passed - should handle this message!")
        return True
    
    async def handle_hydration_reminder(self, bot, room_id: str) -> bool:
        """
        Handle a hydration reminder message by incrementing counter and responding.
        Returns True if handled successfully, False otherwise.
        """
        try:
            # Increment counter
            self._counter += 1
            logger.info(f"Hydration reminder detected! Count is now: {self._counter}")
            
            # Save the updated counter
            self._save_counter()
            
            # Generate response using BAML (synchronous call)
            response = b.GenerateHydrationReminderResponse(count=self._counter)
            
            if response and response.message:
                # Send the response to the channel
                await bot.send_message(room_id, response.message)
                logger.info(f"Sent hydration reminder response #{self._counter}: {response.message[:100]}...")
                return True
            else:
                logger.error("No response generated from BAML function")
                return False
                
        except Exception as e:
            logger.error(f"Error handling hydration reminder: {e}")
            return False
    
    @property
    def current_count(self) -> int:
        """Get the current counter value."""
        return self._counter
    
    def reset_counter(self) -> int:
        """Reset the counter to 0 and return the previous value."""
        previous_count = self._counter
        self._counter = 0
        self._save_counter()
        logger.info(f"Reset hydration reminder counter from {previous_count} to 0")
        return previous_count 