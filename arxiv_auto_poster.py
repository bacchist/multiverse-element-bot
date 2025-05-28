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
        max_posts_per_day: int = 999,  # Effectively no limit
        posting_interval: timedelta = timedelta(hours=4),
        discovery_interval: timedelta = timedelta(hours=4)
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
        self.queue: List = []
        self.posted_today: List[str] = []  # arXiv IDs posted today
        self.posted_papers: Set[str] = set()  # All posted papers (persistent)
        self.last_discovery: Optional[datetime] = None
        self.last_posting: Optional[datetime] = None
        self.posted_total = 0
        
        # Posting coordination (CRITICAL FIX: Prevent double posting)
        self._posting_lock = asyncio.Lock()
        
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
                
                # Load posted papers set (CRITICAL FIX)
                posted_papers_list = state.get('posted_papers', [])
                self.posted_papers = set(posted_papers_list)
                
                # Load queue
                queue_data = state.get('queue', [])
                self.queue = []
                for paper_data in queue_data:
                    try:
                        paper = self._deserialize_paper(paper_data)
                        self.queue.append(paper)
                    except Exception as e:
                        logger.warning(f"Error deserializing paper from queue: {e}")
                        continue
                
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
                
                logger.info(f"Loaded auto-poster state: {self.posted_total} total posts, {len(self.posted_today)} today, {len(self.posted_papers)} posted papers tracked, {len(self.queue)} papers in queue")
                
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

    def _serialize_paper(self, paper) -> Dict[str, Any]:
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

    def _deserialize_paper(self, paper_data: Dict[str, Any]):
        """Deserialize a paper object from JSON-compatible dict."""
        if ArxivPaper is None:
            raise ImportError("ArxivPaper not available")
            
        from datetime import datetime
        
        paper = ArxivPaper(
            arxiv_id=paper_data['arxiv_id'],
            title=paper_data['title'],
            authors=paper_data['authors'],
            abstract=paper_data['abstract'],
            categories=paper_data['categories'],
            published=datetime.fromisoformat(paper_data['published']),
            updated=datetime.fromisoformat(paper_data['updated']),
            pdf_url=paper_data['pdf_url'],
            arxiv_url=paper_data['arxiv_url'],
            doi=paper_data.get('doi'),
            altmetric_score=paper_data.get('altmetric_score'),
            altmetric_data=paper_data.get('altmetric_data'),
        )
        
        # Set priority score directly to avoid recalculation
        paper.priority_score = paper_data.get('priority_score', 0.0)
        
        return paper

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
                    
                    # Re-rank existing queue with updated priority scores
                    for paper in self.queue:
                        paper.priority_score = paper._calculate_priority()
                    
                    # Add new papers to queue
                    self.queue.extend(truly_new)
                    
                    # Sort entire queue by updated priority scores
                    self.queue.sort(key=lambda p: p.priority_score, reverse=True)
                    
                    # Keep queue manageable
                    self.queue = self.queue[:50]
                    
                    self.last_discovery = now
                    self.save_state()
                    
                    logger.info(f"Discovery complete: {len(truly_new)} new papers added, queue re-ranked, now has {len(self.queue)} papers")
                else:
                    # Even if no new papers, re-rank existing queue
                    if self.queue:
                        for paper in self.queue:
                            paper.priority_score = paper._calculate_priority()
                        self.queue.sort(key=lambda p: p.priority_score, reverse=True)
                        self.save_state()
                        logger.info(f"No new papers found, but re-ranked existing queue of {len(self.queue)} papers")
                    
                    self.last_discovery = now
            
            # Check if we should post a paper (with lock to coordinate with manual posts)
            async with self._posting_lock:
                should_post = (
                    len(self.queue) > 0 and
                    len(self.posted_today) < self.max_posts_per_day and
                    (self.last_posting is None or (now - self.last_posting) >= self.posting_interval)
                )
                
                if should_post:
                    # Post directly within the lock (avoid calling post_next_paper to prevent deadlock)
                    try:
                        # Get the highest priority paper
                        paper = self.queue.pop(0)
                        
                        # Get the actual room ID for the target channel
                        target_room_id = self._get_target_room_id()
                        if not target_room_id:
                            logger.error(f"Cannot post paper: target room '{self.target_channel}' not found or bot not in room")
                            return
                        
                        # Generate and send the post
                        message = await self._format_paper_for_posting(paper)
                        await self.bot.send_message(target_room_id, message)
                        
                        # Update tracking
                        self.posted_today.append(paper.arxiv_id)
                        self.posted_papers.add(paper.arxiv_id)
                        self.posted_total += 1
                        self.last_posting = datetime.now(timezone.utc)
                        self.save_state()
                        
                        logger.info(f"Posted paper (auto): {paper.title[:50]}... (Score: {paper.priority_score:.1f})")
                        
                    except Exception as e:
                        logger.error(f"Error posting paper (auto): {e}")
                
        except Exception as e:
            logger.error(f"Error in auto-poster maintenance cycle: {e}")

    async def discover_papers(self) -> List:
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
            
            # Re-rank papers with updated priority scores
            for paper in papers:
                paper.priority_score = paper._calculate_priority()
            
            # Sort by updated priority scores
            papers.sort(key=lambda p: p.priority_score, reverse=True)
            
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

    def _filter_trending_papers(self, papers: List) -> List:
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
            
            # Criterion 3: Any Altmetric data (even minimal social attention)
            elif paper.altmetric_score and paper.altmetric_score > 0:
                is_trending = True
                reasons.append(f"Has social attention (Altmetric: {paper.altmetric_score:.1f})")
            
            # Criterion 4: Very high priority score (recent papers in hot AI categories)
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
            
            # Criterion 5: Quality papers in top AI venues/categories (fallback for when no Altmetric data)
            elif not any(p.altmetric_score and p.altmetric_score > 0 for p in papers):
                # Only use this fallback when NO papers have Altmetric data
                from datetime import datetime, timezone
                hours_old = (datetime.now(timezone.utc) - paper.published).total_seconds() / 3600
                
                # Very recent papers in premium AI categories
                if hours_old < 24:
                    premium_categories = ['cs.AI', 'cs.LG']
                    if any(cat in paper.categories for cat in premium_categories):
                        is_trending = True
                        reasons.append(f"Recent premium AI paper ({hours_old:.1f}h old)")
                
                # Or papers with high priority scores in any AI category
                elif paper.priority_score >= 60.0:
                    ai_categories = ['cs.AI', 'cs.LG', 'cs.CL', 'cs.CV', 'cs.NE', 'stat.ML']
                    if any(cat in paper.categories for cat in ai_categories):
                        is_trending = True
                        reasons.append(f"Quality AI paper (Priority: {paper.priority_score:.1f})")
            
            if is_trending:
                trending_papers.append(paper)
                logger.debug(f"✅ Trending: {paper.title[:50]}... - {'; '.join(reasons)}")
            else:
                logger.debug(f"❌ Not trending: {paper.title[:50]}... (Priority: {paper.priority_score:.1f}, Altmetric: {paper.altmetric_score or 0:.1f})")
        
        # Sort by priority score to ensure best papers are posted first
        trending_papers.sort(key=lambda p: p.priority_score, reverse=True)
        
        # If we still have no papers, take the top 3 by priority score as a last resort
        if not trending_papers and papers:
            logger.info("No papers met trending criteria, falling back to top papers by priority")
            trending_papers = sorted(papers, key=lambda p: p.priority_score, reverse=True)[:3]
            for paper in trending_papers:
                logger.debug(f"✅ Fallback: {paper.title[:50]}... (Priority: {paper.priority_score:.1f})")
        
        return trending_papers

    async def post_next_paper(self) -> bool:
        """
        Post the next paper from the queue (for manual commands).
        
        Returns:
            True if a paper was posted successfully
        """
        # CRITICAL FIX: Use lock to prevent simultaneous posting
        async with self._posting_lock:
            if not self.enabled or not self.queue:
                return False
                
            if len(self.posted_today) >= self.max_posts_per_day:
                logger.info("Daily posting limit reached")
                return False
                
            try:
                # Get the highest priority paper
                paper = self.queue.pop(0)
                
                # Get the actual room ID for the target channel
                target_room_id = self._get_target_room_id()
                if not target_room_id:
                    logger.error(f"Cannot post paper: target room '{self.target_channel}' not found or bot not in room")
                    return False
                
                # Generate and send the post
                message = await self._format_paper_for_posting(paper)
                await self.bot.send_message(target_room_id, message)
                
                # Update tracking
                self.posted_today.append(paper.arxiv_id)
                self.posted_papers.add(paper.arxiv_id)  # Prevent re-posting
                self.posted_total += 1
                self.last_posting = datetime.now(timezone.utc)
                self.save_state()
                
                logger.info(f"Posted paper (manual): {paper.title[:50]}... (Score: {paper.priority_score:.1f})")
                return True
                
            except Exception as e:
                logger.error(f"Error posting paper (manual): {e}")
                return False

    async def _format_paper_for_posting(self, paper) -> str:
        """Format a paper for posting to Matrix."""
        # Generate insightful comment using BAML
        comment = await self._generate_paper_comment(paper)
        
        # Add Altmetric context if it's particularly noteworthy
        trending_context = ""
        if paper.altmetric_score and paper.altmetric_score >= 5.0:
            trending_context = f" (🔥 Trending: {paper.altmetric_score:.0f} Altmetric score)"
        elif paper.altmetric_data:
            # Check for notable social engagement
            tweets = paper.altmetric_data.get('cited_by_tweeters_count', 0)
            reddit = paper.altmetric_data.get('cited_by_rdts_count', 0)
            news = paper.altmetric_data.get('cited_by_feeds_count', 0)
            
            if tweets >= 10:
                trending_context = f" (🐦 {tweets} tweets)"
            elif reddit >= 3:
                trending_context = f" (🔴 Popular on Reddit)"
            elif news >= 2:
                trending_context = f" (📰 News coverage)"
        
        # Simple, concise format
        message = f"""🤖 **{paper.title}**{trending_context}

{comment}

🔗 {paper.arxiv_url}"""
        
        return message

    async def _generate_paper_comment(self, paper) -> str:
        """Generate a thoughtful comment about the paper using BAML with full paper content."""
        try:
            # Try to use BAML for comment generation with full paper content
            from baml_client.sync_client import b
            
            # Prepare context for more insightful comments
            authors_str = ", ".join(paper.authors[:2])  # Just first 2 authors
            categories_str = ", ".join(paper.categories[:2])
            
            # Focus on what makes this paper interesting/trending
            trending_info = ""
            if paper.altmetric_score and paper.altmetric_score >= 5.0:
                trending_info = f"High social engagement (Altmetric: {paper.altmetric_score:.1f}). "
            elif paper.altmetric_data:
                tweets = paper.altmetric_data.get('cited_by_tweeters_count', 0)
                if tweets >= 5:
                    trending_info = f"Getting attention on social media ({tweets} tweets). "
            
            logger.info(f"Generating enhanced comment with full paper content for: {paper.title[:50]}...")
            
            # Step 1: Try to crawl the full paper content (following prepare_thread_data pattern)
            try:
                # Check if we have access to the crawler
                crawler = getattr(self.bot, 'crawler', None)
                if crawler:
                    from crawl4ai import CrawlerRunConfig
                    
                    # Try the HTML version first (better for parsing)
                    html_url = paper.arxiv_url.replace('/abs/', '/html/')
                    
                    logger.debug(f"Attempting to crawl ArXiv HTML: {html_url}")
                    await crawler.start()
                    result = await crawler.arun(url=html_url, config=CrawlerRunConfig(
                        exclude_external_images=False,
                        wait_for_images=True
                    ))
                    
                    if result and hasattr(result, 'markdown') and result.markdown:
                        logger.debug(f"Successfully crawled paper content ({len(result.markdown)} chars)")
                        
                        # Step 2: Parse the paper content (following prepare_thread_data pattern)
                        parsed_paper = b.ParsePaper(result.markdown)
                        
                        # Step 3: Summarize the parsed paper (following prepare_thread_data pattern)
                        paper_summary = b.WritePaperSummary(parsed_paper)
                        summary_text = "\n\n".join([p.text for p in paper_summary.summary])
                        
                        logger.debug(f"Generated paper summary ({len(summary_text)} chars)")
                        
                        # Step 4: Generate comment based on the rich summary
                        result = b.GenerateEnhancedPaperComment(
                            title=paper.title,
                            authors=authors_str,
                            paper_summary=summary_text,
                            categories=categories_str,
                            altmetric_info=trending_info
                        )
                        
                        logger.info(f"Enhanced comment from full content: {result.comment[:100]}...")
                        return result.comment
                    else:
                        logger.debug("No content from HTML crawl, falling back to abstract-based approach")
                else:
                    logger.debug("No crawler available, falling back to abstract-based approach")
                    
            except Exception as crawl_error:
                logger.debug(f"Crawling failed ({crawl_error}), falling back to abstract-based approach")
            
            # Fallback: Use the enhanced abstract-based approach
            logger.debug("Using enhanced abstract-based comment generation...")
            
            # Step 1: Create a detailed summary from the abstract (following the summarize pattern)
            summary_result = b.SummarizeArxivPaper(
                title=paper.title,
                authors=authors_str,
                abstract=paper.abstract,
                categories=categories_str,
                altmetric_info=trending_info
            )
            
            logger.debug(f"Abstract-based summary: {summary_result.comment[:100]}...")
            
            # Step 2: Generate an enhanced comment based on the summary
            result = b.GenerateEnhancedPaperComment(
                title=paper.title,
                authors=authors_str,
                paper_summary=summary_result.comment,
                categories=categories_str,
                altmetric_info=trending_info
            )
            
            logger.info(f"Enhanced comment from abstract: {result.comment[:100]}...")
            return result.comment
            
        except Exception as e:
            logger.error(f"Enhanced comment generation failed for paper '{paper.title[:50]}...': {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Fallback to the original simple BAML function
            try:
                logger.info("Falling back to simple BAML comment generation...")
                from baml_client.sync_client import b
                result = b.GeneratePaperComment(
                    title=paper.title,
                    authors=authors_str,
                    abstract=paper.abstract[:400],
                    categories=categories_str,
                    altmetric_info=trending_info,
                    context="Generate a concise, insightful comment (1-2 sentences) about why this research is interesting or significant. Focus on the key insight, potential impact, or novel approach rather than just describing what it does."
                )
                logger.info(f"Simple BAML comment generated: {result.comment[:100]}...")
                return result.comment
            except Exception as e2:
                logger.error(f"Simple BAML comment also failed: {e2}")
                
                # Final fallback to simple comment based on categories
                if any(cat in ['cs.AI', 'cs.LG'] for cat in paper.categories):
                    fallback = "Interesting new approach in AI/ML research worth checking out."
                elif 'cs.CL' in paper.categories:
                    fallback = "New developments in natural language processing."
                elif 'cs.CV' in paper.categories:
                    fallback = "Novel computer vision research with potential applications."
                else:
                    fallback = "New research that's gaining attention in the AI community."
                
                logger.info(f"Using fallback comment: {fallback}")
                return fallback

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

    def _get_target_room_id(self) -> Optional[str]:
        """
        Get the actual room ID for the target channel.
        
        Returns:
            The room ID if found, None otherwise
        """
        # If target_channel is already a room ID, use it directly
        if self.target_channel.startswith('!'):
            return self.target_channel
        
        # Look for the room by alias in bot.rooms
        if hasattr(self.bot, 'rooms'):
            for room_id, room in self.bot.rooms.items():
                # Check if this room matches our target alias
                room_aliases = getattr(room, 'canonical_alias', None)
                alt_aliases = getattr(room, 'alternative_aliases', []) or []
                
                # Check canonical alias
                if room_aliases == self.target_channel:
                    return room_id
                
                # Check alternative aliases
                if self.target_channel in alt_aliases:
                    return room_id
                
                # Also check room name as fallback
                room_name = getattr(room, 'display_name', None) or getattr(room, 'name', None)
                if room_name and f"#{room_name}:themultiverse.school" == self.target_channel:
                    return room_id
        
        logger.warning(f"Could not find room ID for target channel: {self.target_channel}")
        return None 