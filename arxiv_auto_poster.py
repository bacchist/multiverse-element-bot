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
from typing import List, Optional, Dict, Any, Set
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
        self.posted_papers: Set[str] = set()  # All posted papers (persistent)
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
                
                logger.info(f"Loaded auto-poster state: {self.posted_total} total posts, {len(self.posted_today)} today, {len(self.queue)} papers in queue")
                
        except Exception as e:
            logger.warning(f"Error loading auto-poster state: {e}")

    def save_state(self):
        """Save persistent state to file."""
        try:
            # Serialize queue
            queue_data = []
            for paper in self.queue:
                try:
                    queue_data.append(self._serialize_paper(paper))
                except Exception as e:
                    logger.warning(f"Error serializing paper for queue: {e}")
                    continue
            
            state = {
                'posted_total': self.posted_total,
                'posted_today': self.posted_today,
                'posted_papers': list(self.posted_papers),
                'queue': queue_data,
                'last_reset': datetime.now(timezone.utc).date().isoformat(),
                'last_discovery': self.last_discovery.isoformat() if self.last_discovery else None,
                'last_posting': self.last_posting.isoformat() if self.last_posting else None
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving auto-poster state: {e}")

    def _serialize_paper(self, paper: ArxivPaper) -> Dict[str, Any]:
        """Serialize a paper object to JSON-compatible dict."""
        return {
            'arxiv_id': paper.arxiv_id,
            'title': paper.title,
            'authors': paper.authors,
            'abstract': paper.abstract,
            'categories': paper.categories,
            'published': paper.published.isoformat(),
            'updated': paper.updated.isoformat(),
            'pdf_url': paper.pdf_url,
            'arxiv_url': paper.arxiv_url,
            'doi': paper.doi,
            'altmetric_score': paper.altmetric_score,
            'altmetric_data': paper.altmetric_data,
            'priority_score': paper.priority_score
        }

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
                new_papers = await self.discover_papers()
                if new_papers:
                    # Filter out papers we've already posted or queued
                    existing_ids = {p.arxiv_id for p in self.queue} | set(self.posted_papers)
                    truly_new = [p for p in new_papers if p.arxiv_id not in existing_ids]
                    
                    # Add to queue (sorted by priority)
                    self.queue.extend(truly_new)
                    self.queue.sort(key=lambda p: p.priority_score, reverse=True)
                    
                    # Keep queue manageable
                    self.queue = self.queue[:50]
                    
                    self.last_discovery = now
                    self.save_state()
                    
                    logger.info(f"Discovery complete: {len(truly_new)} new papers added, queue now has {len(self.queue)} papers")
            
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

    async def discover_papers(self) -> List['ArxivPaper']:
        """Discover new trending papers."""
        try:
            logger.info("🔍 Discovering new trending papers...")
            
            if ArxivAltmetricTracker is None:
                logger.error("ArxivAltmetricTracker not available")
                return []
            
            async with ArxivAltmetricTracker() as tracker:
                papers = await tracker.get_trending_papers(
                    days_back=3,
                    count=20,  # Get more papers to filter from
                    include_altmetric=True
                )
            
            if not papers:
                logger.warning("No papers found during discovery")
                return []
            
            # Log Altmetric statistics for monitoring
            papers_with_altmetric = [p for p in papers if p.altmetric_score and p.altmetric_score > 0]
            if papers_with_altmetric:
                avg_score = sum(p.altmetric_score for p in papers_with_altmetric if p.altmetric_score) / len(papers_with_altmetric)
                max_score = max(p.altmetric_score for p in papers_with_altmetric if p.altmetric_score)
                logger.info(f"📊 Altmetric coverage: {len(papers_with_altmetric)}/{len(papers)} papers ({len(papers_with_altmetric)/len(papers)*100:.1f}%)")
                logger.info(f"📊 Altmetric scores - Avg: {avg_score:.1f}, Max: {max_score:.1f}")
            else:
                logger.warning("⚠️ No papers found with Altmetric data")
            
            # Filter out already posted papers
            new_papers = [p for p in papers if p.arxiv_id not in self.posted_papers]
            
            if len(new_papers) < len(papers):
                logger.info(f"📝 Filtered out {len(papers) - len(new_papers)} already posted papers")
            
            # Apply trending criteria - only keep papers that meet trending thresholds
            trending_papers = self._filter_trending_papers(new_papers)
            
            if len(trending_papers) < len(new_papers):
                logger.info(f"🔥 Filtered to {len(trending_papers)} truly trending papers (from {len(new_papers)} candidates)")
            
            # Log top papers for monitoring
            if trending_papers:
                logger.info(f"🏆 Top trending paper: '{trending_papers[0].title[:60]}...' (Priority: {trending_papers[0].priority_score:.1f}, Altmetric: {trending_papers[0].altmetric_score or 0:.1f})")
            
            return trending_papers
            
        except Exception as e:
            logger.error(f"Error discovering papers: {e}")
            return []

    def _filter_trending_papers(self, papers: List['ArxivPaper']) -> List['ArxivPaper']:
        """Filter papers to only include those that meet trending criteria."""
        trending_papers = []
        
        for paper in papers:
            is_trending = False
            reasons = []
            
            # Criterion 1: High Altmetric score (strong social engagement)
            if paper.altmetric_score and paper.altmetric_score >= 5.0:
                is_trending = True
                reasons.append(f"High Altmetric score ({paper.altmetric_score:.1f})")
            
            # Criterion 2: Medium Altmetric score with social media engagement
            elif paper.altmetric_score and paper.altmetric_score >= 2.0 and paper.altmetric_data:
                # Check for actual social engagement
                tweets = paper.altmetric_data.get('cited_by_tweeters_count', 0)
                reddit = paper.altmetric_data.get('cited_by_rdts_count', 0)
                news = paper.altmetric_data.get('cited_by_feeds_count', 0)
                
                if tweets >= 3 or reddit >= 1 or news >= 1:
                    is_trending = True
                    engagement = []
                    if tweets >= 3: engagement.append(f"{tweets} tweets")
                    if reddit >= 1: engagement.append(f"{reddit} Reddit")
                    if news >= 1: engagement.append(f"{news} news")
                    reasons.append(f"Social engagement: {', '.join(engagement)}")
            
            # Criterion 3: Very high priority score (even without Altmetric)
            # This catches very recent papers in hot AI categories
            elif paper.priority_score >= 80.0:
                is_trending = True
                reasons.append(f"High priority score ({paper.priority_score:.1f})")
                
                # Check if it's a very recent paper in a hot category
                from datetime import datetime, timezone
                hours_old = (datetime.now(timezone.utc) - paper.published).total_seconds() / 3600
                if hours_old < 12:
                    hot_categories = ['cs.AI', 'cs.LG', 'cs.CL', 'cs.CV']
                    if any(cat in paper.categories for cat in hot_categories):
                        reasons.append(f"Recent paper ({hours_old:.1f}h old) in hot category")
            
            # Criterion 4: Papers with any Altmetric data in very recent timeframe
            # (catches breaking papers that just started getting attention)
            elif paper.altmetric_score and paper.altmetric_score > 0:
                from datetime import datetime, timezone
                hours_old = (datetime.now(timezone.utc) - paper.published).total_seconds() / 3600
                if hours_old < 24:
                    is_trending = True
                    reasons.append(f"Recent paper with emerging attention (Altmetric: {paper.altmetric_score:.1f})")
            
            if is_trending:
                trending_papers.append(paper)
                logger.debug(f"✅ Trending: {paper.title[:50]}... - {'; '.join(reasons)}")
            else:
                logger.debug(f"❌ Not trending: {paper.title[:50]}... (Priority: {paper.priority_score:.1f}, Altmetric: {paper.altmetric_score or 0:.1f})")
        
        # Sort by priority score to ensure best papers are posted first
        trending_papers.sort(key=lambda p: p.priority_score, reverse=True)
        
        return trending_papers

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