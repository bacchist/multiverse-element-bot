#!/usr/bin/env python3
"""
ArXiv Auto-Poster for Matrix Bot

An optional module that automatically discovers trending AI papers and posts them
to Matrix channels. Designed to be completely isolated from core bot functionality.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
import niobot

try:
    from arxiv_tracker import ArxivAltmetricTracker, ArxivPaper
except ImportError:
    # Graceful fallback if arxiv_tracker is not available
    ArxivAltmetricTracker = None
    ArxivPaper = None

# Configure logging for this module
logger = logging.getLogger(__name__)

class ArxivAutoPoster:
    """Automatically discovers and posts trending AI papers to Matrix channels."""
    
    def __init__(
        self, 
        bot: niobot.NioBot,
        target_channel: str = "#ai-papers:themultiverse.school",
        max_posts_per_day: int = 5,
        posting_interval: timedelta = timedelta(hours=4),
        discovery_interval: timedelta = timedelta(hours=6)
    ):
        """
        Initialize the auto-poster.
        
        Args:
            bot: The Matrix bot instance
            target_channel: Channel to post papers to
            max_posts_per_day: Maximum papers to post per day
            posting_interval: Minimum time between posts
            discovery_interval: How often to discover new papers
        """
        self.bot = bot
        self.target_channel = target_channel
        self.max_posts_per_day = max_posts_per_day
        self.posting_interval = posting_interval
        self.discovery_interval = discovery_interval
        
        # State tracking
        self.queue: List[ArxivPaper] = []
        self.posted_today: List[str] = []  # arXiv IDs posted today
        self.last_discovery: Optional[datetime] = None
        self.last_posting: Optional[datetime] = None
        self.posted_total = 0
        
        # Persistence
        self.state_file = Path("arxiv_auto_poster_state.json")
        self.load_state()
        
        # Check if dependencies are available
        self.enabled = ArxivAltmetricTracker is not None
        if not self.enabled:
            logger.warning("ArXiv auto-poster disabled: arxiv_tracker module not available")

    def load_state(self):
        """Load persistent state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                
                self.posted_total = state.get('posted_total', 0)
                self.posted_today = state.get('posted_today', [])
                
                # Check if we need to reset daily counter
                last_reset = state.get('last_reset')
                if last_reset:
                    last_reset_date = datetime.fromisoformat(last_reset).date()
                    today = datetime.now(timezone.utc).date()
                    if last_reset_date < today:
                        self.posted_today = []
                
                # Load timestamps
                if state.get('last_discovery'):
                    self.last_discovery = datetime.fromisoformat(state['last_discovery'])
                if state.get('last_posting'):
                    self.last_posting = datetime.fromisoformat(state['last_posting'])
                
                logger.info(f"Loaded auto-poster state: {self.posted_total} total posts, {len(self.posted_today)} today")
                
        except Exception as e:
            logger.warning(f"Error loading auto-poster state: {e}")

    def save_state(self):
        """Save persistent state to file."""
        try:
            state = {
                'posted_total': self.posted_total,
                'posted_today': self.posted_today,
                'last_reset': datetime.now(timezone.utc).date().isoformat(),
                'last_discovery': self.last_discovery.isoformat() if self.last_discovery else None,
                'last_posting': self.last_posting.isoformat() if self.last_posting else None
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving auto-poster state: {e}")

    async def run_maintenance_cycle(self):
        """Run a maintenance cycle - discover papers and post if needed."""
        if not self.enabled:
            return
            
        try:
            now = datetime.now(timezone.utc)
            
            # Check if we should discover new papers
            should_discover = (
                self.last_discovery is None or 
                (now - self.last_discovery) >= self.discovery_interval
            )
            
            if should_discover:
                await self.discover_papers()
            
            # Check if we should post a paper
            should_post = (
                len(self.queue) > 0 and
                len(self.posted_today) < self.max_posts_per_day and
                (self.last_posting is None or (now - self.last_posting) >= self.posting_interval)
            )
            
            if should_post:
                await self.post_next_paper()
                
        except Exception as e:
            logger.error(f"Error in auto-poster maintenance cycle: {e}")

    async def discover_papers(self, days_back: int = 3) -> int:
        """
        Discover new trending papers and add them to the queue.
        
        Args:
            days_back: Number of days to look back for papers
            
        Returns:
            Number of new papers added to queue
        """
        if not self.enabled:
            return 0
            
        try:
            logger.info(f"Discovering new papers from last {days_back} days...")
            
            async with ArxivAltmetricTracker() as tracker:
                # Fetch trending papers
                papers = await tracker.get_trending_papers(
                    days_back=days_back,
                    count=20,  # Get more papers to have good selection
                    include_altmetric=True
                )
            
            # Filter out papers we've already posted or queued
            existing_ids = {p.arxiv_id for p in self.queue} | set(self.posted_today)
            new_papers = [p for p in papers if p.arxiv_id not in existing_ids]
            
            # Add to queue (sorted by priority)
            self.queue.extend(new_papers)
            self.queue.sort(key=lambda p: p.priority_score, reverse=True)
            
            # Keep queue manageable
            self.queue = self.queue[:50]
            
            self.last_discovery = datetime.now(timezone.utc)
            self.save_state()
            
            logger.info(f"Discovery complete: {len(new_papers)} new papers added, queue now has {len(self.queue)} papers")
            return len(new_papers)
            
        except Exception as e:
            logger.error(f"Error discovering papers: {e}")
            return 0

    async def post_next_paper(self) -> bool:
        """
        Post the next paper from the queue.
        
        Returns:
            True if a paper was posted successfully
        """
        if not self.enabled or not self.queue:
            return False
            
        if len(self.posted_today) >= self.max_posts_per_day:
            logger.info("Daily posting limit reached")
            return False
            
        try:
            # Get the highest priority paper
            paper = self.queue.pop(0)
            
            # Generate and send the post
            message = self._format_paper_for_posting(paper)
            await self.bot.send_message(self.target_channel, message)
            
            # Update tracking
            self.posted_today.append(paper.arxiv_id)
            self.posted_total += 1
            self.last_posting = datetime.now(timezone.utc)
            self.save_state()
            
            logger.info(f"Posted paper: {paper.title[:50]}... (Score: {paper.priority_score:.1f})")
            return True
            
        except Exception as e:
            logger.error(f"Error posting paper: {e}")
            return False

    def _format_paper_for_posting(self, paper: ArxivPaper) -> str:
        """Format a paper for posting to Matrix."""
        # Truncate title if too long
        title = paper.title[:100] + "..." if len(paper.title) > 100 else paper.title
        
        # Format authors (show first 3)
        if len(paper.authors) <= 3:
            authors_str = ", ".join(paper.authors)
        else:
            authors_str = ", ".join(paper.authors[:3]) + f" et al. ({len(paper.authors)} total)"
        
        # Truncate authors if too long
        if len(authors_str) > 120:
            authors_str = authors_str[:117] + "..."
        
        # Categories (show main AI categories only)
        ai_categories = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "stat.ML"]
        main_categories = [cat for cat in paper.categories if cat in ai_categories]
        categories_str = ", ".join(main_categories[:2])
        
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
                
                if mentions:
                    altmetric_info += f" ({', '.join(mentions)})"
        
        # Truncate abstract
        abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
        
        # Generate comment using BAML if available
        comment = self._generate_paper_comment(paper)
        
        # Format the message
        message = f"""🤖 **Trending AI Paper**

**{title}**

{comment}

👥 {authors_str}
📅 {paper.published.strftime('%Y-%m-%d')} | 🏷️ {categories_str}
{altmetric_info}

{abstract}

🔗 [arXiv]({paper.arxiv_url}) | [PDF]({paper.pdf_url})"""
        
        return message

    def _generate_paper_comment(self, paper: ArxivPaper) -> str:
        """Generate a thoughtful comment about the paper using BAML."""
        try:
            # Try to use BAML for comment generation
            from baml_client.sync_client import b
            
            # Prepare context
            authors_str = ", ".join(paper.authors[:3])
            categories_str = ", ".join(paper.categories[:3])
            altmetric_info = f"Altmetric score: {paper.altmetric_score:.1f}" if paper.altmetric_score else "No Altmetric data"
            
            result = b.GeneratePaperComment(
                title=paper.title,
                authors=authors_str,
                abstract=paper.abstract[:500],  # Truncate for API limits
                categories=categories_str,
                altmetric_info=altmetric_info,
                context="Sharing with AI research community at The Multiverse School"
            )
            
            return result.comment
            
        except Exception as e:
            logger.debug(f"Could not generate comment with BAML: {e}")
            # Fallback to simple comment
            return "New research worth checking out from the AI community."

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the auto-poster."""
        now = datetime.now(timezone.utc)
        
        # Calculate next scheduled times
        next_discovery = None
        if self.last_discovery:
            next_discovery = (self.last_discovery + self.discovery_interval).strftime('%Y-%m-%d %H:%M UTC')
        
        next_posting = None
        if self.last_posting:
            next_posting = (self.last_posting + self.posting_interval).strftime('%Y-%m-%d %H:%M UTC')
        
        return {
            'enabled': self.enabled,
            'queue_size': len(self.queue),
            'posted_total': self.posted_total,
            'posts_today': len(self.posted_today),
            'max_posts_per_day': self.max_posts_per_day,
            'target_channel': self.target_channel,
            'last_discovery': self.last_discovery.strftime('%Y-%m-%d %H:%M UTC') if self.last_discovery else None,
            'last_posting': self.last_posting.strftime('%Y-%m-%d %H:%M UTC') if self.last_posting else None,
            'next_discovery': next_discovery,
            'next_posting': next_posting
        } 