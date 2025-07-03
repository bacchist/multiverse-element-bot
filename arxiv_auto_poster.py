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
        self.pool: List = []  # Renamed from queue - papers stored for up to 2 weeks
        self.candidates: List = []  # Top 5 papers elevated for posting consideration
        self.blacklist: Set[str] = set()  # Papers rejected/filtered to avoid re-evaluation
        self.posted_today: List[str] = []  # arXiv IDs posted today
        self.posted_papers: Set[str] = set()  # All posted papers (persistent)
        self.last_discovery: Optional[datetime] = None
        self.last_posting: Optional[datetime] = None
        self.posted_total = 0
        
        # Pool management settings
        self.pool_retention_days = 14  # Keep papers for 2 weeks
        self.max_pool_size = 200  # Increased from 50 to accommodate longer retention
        self.max_candidates = 5  # Number of papers elevated to candidate status
        
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
                
                # Load blacklist
                blacklist_list = state.get('blacklist', [])
                self.blacklist = set(blacklist_list)
                
                # Load pool (formerly queue)
                pool_data = state.get('pool', state.get('queue', []))  # Backward compatibility
                self.pool = []
                for paper_data in pool_data:
                    try:
                        paper = self._deserialize_paper(paper_data)
                        self.pool.append(paper)
                    except Exception as e:
                        logger.warning(f"Error deserializing paper from pool: {e}")
                        continue
                
                # Load candidates
                candidates_data = state.get('candidates', [])
                self.candidates = []
                for paper_data in candidates_data:
                    try:
                        paper = self._deserialize_paper(paper_data)
                        self.candidates.append(paper)
                    except Exception as e:
                        logger.warning(f"Error deserializing candidate paper: {e}")
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
                
                logger.info(f"Loaded auto-poster state: {self.posted_total} total posts, {len(self.posted_today)} today, {len(self.posted_papers)} posted papers tracked, {len(self.pool)} papers in pool, {len(self.candidates)} candidates, {len(self.blacklist)} blacklisted")
                
        except Exception as e:
            logger.warning(f"Error loading auto-poster state: {e}")

    def save_state(self):
        """Save persistent state to file."""
        try:
            # Serialize pool
            pool_data = []
            for paper in self.pool:
                try:
                    pool_data.append(self._serialize_paper(paper))
                except Exception as e:
                    logger.warning(f"Error serializing paper for pool: {e}")
                    continue
            
            # Serialize candidates
            candidates_data = []
            for paper in self.candidates:
                try:
                    candidates_data.append(self._serialize_paper(paper))
                except Exception as e:
                    logger.warning(f"Error serializing candidate paper: {e}")
                    continue
            
            state = {
                'posted_total': self.posted_total,
                'posted_today': self.posted_today,
                'posted_papers': list(self.posted_papers),
                'blacklist': list(self.blacklist),
                'pool': pool_data,
                'candidates': candidates_data,
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
            'priority_score': paper.priority_score,
            'accessibility': paper.accessibility
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
            accessibility=paper_data.get('accessibility')
        )
        
        # Set priority score directly to avoid recalculation
        paper.priority_score = paper_data.get('priority_score', 0.0)
        
        return paper

    async def refresh_altmetric_for_pool(self):
        """Refresh Altmetric data for papers in the pool using tiered frequency."""
        if ArxivAltmetricTracker is None or not self.pool:
            return
            
        try:
            now = datetime.now(timezone.utc)
            papers_to_refresh = []
            
            # Determine which papers need Altmetric refresh based on age and last refresh
            for paper in self.pool:
                days_old = (now - paper.published).total_seconds() / (24 * 3600)
                
                # Get last refresh time (stored in altmetric_data if available)
                last_refresh = None
                if paper.altmetric_data and 'last_refresh' in paper.altmetric_data:
                    last_refresh = datetime.fromisoformat(paper.altmetric_data['last_refresh'])
                
                should_refresh = False
                
                if last_refresh is None:
                    # Never refreshed - always refresh
                    should_refresh = True
                elif days_old < 2:
                    # Papers < 2 days old: refresh every 4 hours
                    should_refresh = (now - last_refresh).total_seconds() > 4 * 3600
                elif days_old < 7:
                    # Papers 2-7 days old: refresh once per day
                    should_refresh = (now - last_refresh).total_seconds() > 24 * 3600
                else:
                    # Papers > 7 days old: refresh every 3 days
                    should_refresh = (now - last_refresh).total_seconds() > 3 * 24 * 3600
                
                if should_refresh:
                    papers_to_refresh.append(paper)
            
            if not papers_to_refresh:
                logger.info("No papers in pool need Altmetric refresh at this time")
                return
            
            logger.info(f"Refreshing Altmetric data for {len(papers_to_refresh)} papers in pool...")
            refresh_before = [(p.arxiv_id, p.altmetric_score) for p in papers_to_refresh]
            
            async with ArxivAltmetricTracker() as tracker:
                await tracker.enrich_with_altmetric(papers_to_refresh)
            
            # Update last refresh timestamp and log changes
            updates = []
            for (paper_id, old_score), paper in zip(refresh_before, papers_to_refresh):
                # Add refresh timestamp to altmetric_data
                if paper.altmetric_data is None:
                    paper.altmetric_data = {}
                paper.altmetric_data['last_refresh'] = now.isoformat()
                
                if old_score != paper.altmetric_score:
                    updates.append(f"{paper_id}: {old_score or 0:.1f} → {paper.altmetric_score or 0:.1f}")
            
            if updates:
                logger.info(f"Updated Altmetric scores for {len(updates)} papers:")
                for update in updates:
                    logger.info(f"  • {update}")
                
                # Re-sort pool by updated priority scores
                self.pool.sort(key=lambda p: p.priority_score, reverse=True)
                # Save state to persist the updates
                self.save_state()
                logger.info("Pool re-ranked and state saved with updated Altmetric data")
            else:
                logger.info("No changes in Altmetric scores detected")
                
        except Exception as e:
            logger.error(f"Error refreshing Altmetric data: {e}")
            # Continue execution - don't let Altmetric failures break the bot

    async def run_maintenance_cycle(self):
        """Run a maintenance cycle - discover papers, cleanup pool, and post if needed."""
        if not self.enabled:
            return
        try:
            now = datetime.now(timezone.utc)
            
            # Always do pool cleanup and candidate updates
            await self._cleanup_pool()
            
            # Check if we should discover new papers
            should_discover = (
                self.last_discovery is None or 
                (now - self.last_discovery) >= self.discovery_interval
            )
            if should_discover:
                # Refresh Altmetric data for papers in pool using tiered frequency
                await self.refresh_altmetric_for_pool()
                
                # Discover new papers
                new_papers = await self.discover_papers()
                if new_papers:
                    # Add new papers to pool
                    self.pool.extend(new_papers)
                    # Sort entire pool by updated priority scores
                    self.pool.sort(key=lambda p: p.priority_score, reverse=True)
                    # Keep pool manageable
                    self.pool = self.pool[:self.max_pool_size]
                    self.last_discovery = now
                    
                    # Update candidates from refreshed pool
                    await self._update_candidates()
                    self.save_state()
                    logger.info(f"Discovery complete: {len(new_papers)} new papers added to pool, now has {len(self.pool)} papers, {len(self.candidates)} candidates")
                else:
                    # Even if no new papers, update candidates from existing pool
                    await self._update_candidates()
                    self.save_state()
                    logger.info(f"No new papers found, but updated candidates from existing pool of {len(self.pool)} papers")
                    self.last_discovery = now
            
            # Check if we should post a paper (with lock to coordinate with manual posts)
            async with self._posting_lock:
                should_post = (
                    len(self.candidates) > 0 and
                    len(self.posted_today) < self.max_posts_per_day and
                    (self.last_posting is None or (now - self.last_posting) >= self.posting_interval)
                )
                if should_post:
                    # Post directly within the lock (avoid calling post_next_paper to prevent deadlock)
                    try:
                        # Get the highest priority candidate
                        paper = self.candidates.pop(0)
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
                        
                        # Backfill candidates
                        await self._update_candidates()
                        self.save_state()
                        logger.info(f"Posted paper (auto): {paper.title[:50]}... (Score: {paper.priority_score:.1f}, Accessibility: {paper.accessibility})")
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
                    count=30,  # Get more papers to filter from
                    include_altmetric=True
                )
            
            if not papers:
                logger.warning("No papers found during discovery")
                return []
            
            # Filter out papers we've already processed (posted, blacklisted, or in pool)
            existing_ids = (
                {p.arxiv_id for p in self.pool} | 
                set(self.posted_papers) | 
                self.blacklist
            )
            new_papers = [p for p in papers if p.arxiv_id not in existing_ids]
            
            if len(new_papers) < len(papers):
                logger.info(f"📝 Filtered out {len(papers) - len(new_papers)} already processed papers")
            
            if not new_papers:
                logger.info("No new papers to process after filtering")
                return []
            
            # Apply trending criteria (no accessibility filtering here)
            trending_papers = self._filter_trending_papers(new_papers)
            
            if len(trending_papers) < len(new_papers):
                logger.info(f"🔥 Filtered to {len(trending_papers)} truly trending papers (from {len(new_papers)} candidates)")
            
            # Re-rank papers with updated priority scores
            for paper in trending_papers:
                paper.priority_score = paper._calculate_priority()
            
            # Sort by updated priority scores
            trending_papers.sort(key=lambda p: p.priority_score, reverse=True)
            
            # Log statistics
            papers_with_altmetric = [p for p in trending_papers if p.altmetric_score and p.altmetric_score > 0]
            if papers_with_altmetric:
                avg_score = sum(p.altmetric_score for p in papers_with_altmetric if p.altmetric_score) / len(papers_with_altmetric)
                max_score = max(p.altmetric_score for p in papers_with_altmetric if p.altmetric_score)
                logger.info(f"📊 Altmetric coverage: {len(papers_with_altmetric)}/{len(trending_papers)} papers ({len(papers_with_altmetric)/len(trending_papers)*100:.1f}%)")
                logger.info(f"📊 Altmetric scores - Avg: {avg_score:.1f}, Max: {max_score:.1f}")
            
            # Log top paper for monitoring
            if trending_papers:
                top_paper = trending_papers[0]
                logger.info(f"🏆 Top trending paper: '{top_paper.title[:60]}...' (Priority: {top_paper.priority_score:.1f}, Altmetric: {top_paper.altmetric_score or 0:.1f})")
            
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

    async def _cleanup_pool(self):
        """Remove old papers from pool and update candidates."""
        if not self.pool:
            return
            
        now = datetime.now(timezone.utc)
        initial_count = len(self.pool)
        
        # Remove papers older than retention period
        self.pool = [
            paper for paper in self.pool 
            if (now - paper.published).total_seconds() < self.pool_retention_days * 24 * 3600
        ]
        
        removed_count = initial_count - len(self.pool)
        if removed_count > 0:
            logger.info(f"Removed {removed_count} papers older than {self.pool_retention_days} days from pool")
        
        # Update candidates from top papers in pool
        await self._update_candidates()
    
    async def _update_candidates(self):
        """Update the candidates list from the top papers in the pool, assessing accessibility only for potential candidates."""
        if not self.pool:
            self.candidates = []
            return
        
        # Sort pool by priority score
        self.pool.sort(key=lambda p: p.priority_score, reverse=True)
        
        # Get top papers that aren't already posted or blacklisted
        available_papers = [
            paper for paper in self.pool 
            if paper.arxiv_id not in self.posted_papers and paper.arxiv_id not in self.blacklist
        ]
        
        if not available_papers:
            self.candidates = []
            return
        
        # Assess accessibility for top papers that might become candidates
        # We'll check more papers than we need in case some are filtered out
        papers_to_assess = available_papers[:self.max_candidates * 2]  # Check 2x candidates needed
        
        logger.info(f"♿ Assessing accessibility for top {len(papers_to_assess)} papers for candidate selection...")
        
        accessible_candidates = []
        for paper in papers_to_assess:
            # If accessibility is already assessed, use it
            if paper.accessibility is not None:
                if paper.accessibility != "low":
                    accessible_candidates.append(paper)
                    logger.debug(f"✅ Keeping paper with {paper.accessibility} accessibility: {paper.title[:50]}...")
                else:
                    self.blacklist.add(paper.arxiv_id)
                    logger.debug(f"❌ Blacklisting paper with low accessibility: {paper.title[:50]}...")
            else:
                # Assess accessibility for this potential candidate
                accessibility = await self._assess_paper_accessibility(paper)
                paper.accessibility = accessibility
                
                if accessibility != "low":
                    # Recalculate priority score with accessibility multiplier
                    paper.priority_score = paper._calculate_priority()
                    accessible_candidates.append(paper)
                    logger.debug(f"✅ Keeping paper with {accessibility} accessibility: {paper.title[:50]}...")
                else:
                    self.blacklist.add(paper.arxiv_id)
                    logger.debug(f"❌ Blacklisting paper with low accessibility: {paper.title[:50]}...")
            
            # Stop if we have enough candidates
            if len(accessible_candidates) >= self.max_candidates:
                break
        
        # Re-sort by priority score (in case accessibility multipliers changed scores)
        accessible_candidates.sort(key=lambda p: p.priority_score, reverse=True)
        
        # Update candidates to top accessible papers
        old_candidates = {p.arxiv_id for p in self.candidates}
        self.candidates = accessible_candidates[:self.max_candidates]
        new_candidates = {p.arxiv_id for p in self.candidates}
        
        # Log changes
        added = new_candidates - old_candidates
        removed = old_candidates - new_candidates
        
        if added or removed:
            logger.info(f"Updated candidates: +{len(added)} added, -{len(removed)} removed")
            for paper_id in added:
                paper = next(p for p in self.candidates if p.arxiv_id == paper_id)
                logger.info(f"  + Added candidate: {paper.title[:50]}... (Score: {paper.priority_score:.1f}, Accessibility: {paper.accessibility})")
            for paper_id in removed:
                logger.info(f"  - Removed candidate: {paper_id}")
        
        # Log accessibility filtering stats if any papers were assessed
        assessed_papers = [p for p in papers_to_assess if p.accessibility is not None]
        if assessed_papers:
            accessibility_counts = {}
            for paper in assessed_papers:
                acc = paper.accessibility
                accessibility_counts[acc] = accessibility_counts.get(acc, 0) + 1
            logger.info(f"📊 Accessibility distribution for assessed papers: {accessibility_counts}")
    
    def remove_candidate(self, arxiv_id: str) -> bool:
        """
        Manually remove a paper from candidates and add to blacklist.
        
        Args:
            arxiv_id: The arXiv ID of the paper to remove
            
        Returns:
            True if paper was found and removed, False otherwise
        """
        # Find and remove from candidates
        for i, paper in enumerate(self.candidates):
            if paper.arxiv_id == arxiv_id:
                removed_paper = self.candidates.pop(i)
                self.blacklist.add(arxiv_id)
                logger.info(f"Manually removed candidate: {removed_paper.title[:50]}... (added to blacklist)")
                
                # Backfill candidates from pool
                asyncio.create_task(self._update_candidates())
                self.save_state()
                return True
        
        return False 

    async def post_next_paper(self) -> bool:
        """
        Post the next paper from the candidates (for manual commands).
        
        Returns:
            True if a paper was posted successfully
        """
        # CRITICAL FIX: Use lock to prevent simultaneous posting
        async with self._posting_lock:
            if not self.enabled or not self.candidates:
                return False
                
            if len(self.posted_today) >= self.max_posts_per_day:
                logger.info("Daily posting limit reached")
                return False
                
            try:
                # Get the highest priority candidate
                paper = self.candidates.pop(0)
                
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
                
                # Backfill candidates
                await self._update_candidates()
                self.save_state()
                
                logger.info(f"Posted paper (manual): {paper.title[:50]}... (Score: {paper.priority_score:.1f}, Accessibility: {paper.accessibility})")
                return True
                
            except Exception as e:
                logger.error(f"Error posting paper (manual): {e}")
                return False

    async def _format_paper_for_posting(self, paper) -> str:
        """Format a paper for posting to Matrix."""
        # Generate insightful comment using BAML
        comment = await self._generate_paper_comment(paper)
        
        # Simple format with just comment and raw URL for Matrix rich previews
        message = f"""{comment}

{paper.arxiv_url}"""
        
        return message

    async def _generate_paper_comment(self, paper) -> str:
        """Generate a thoughtful comment about the paper using BAML WritePost."""
        try:
            from baml_client.sync_client import b
            
            logger.info(f"Generating post for paper: {paper.title[:50]}...")
            
            # Try to crawl the full paper content (we always have the URL)
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
                        
                        # Parse the full paper content
                        parsed_paper = b.ParsePaper(result.markdown)
                        
                        # Summarize the parsed paper
                        paper_summary = b.WritePaperSummary(parsed_paper)
                        summary_text = "\n\n".join([p.text for p in paper_summary.summary])
                        
                        logger.debug(f"Generated paper summary ({len(summary_text)} chars)")
                        
                        # Generate post using WritePost
                        post = b.WritePost(
                            url=paper.arxiv_url,
                            summary=summary_text
                        )
                        
                        logger.info(f"Generated post from full content: {post.text[:100]}...")
                        return post.text
                    else:
                        logger.warning(f"Failed to crawl paper content from {html_url}")
                else:
                    logger.warning("No crawler available for enhanced post generation")
                    
            except Exception as crawl_error:
                logger.warning(f"Crawling failed for {paper.arxiv_url}: {crawl_error}")
            
            # If crawling failed, use WritePost with just the abstract as summary
            logger.info("Falling back to post generation from abstract...")
            post = b.WritePost(
                url=paper.arxiv_url,
                summary=paper.abstract
            )
            logger.info(f"Generated post from abstract: {post.text[:100]}...")
            return post.text
            
        except Exception as e:
            logger.error(f"Post generation failed for paper '{paper.title[:50]}...': {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
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
        
        # Calculate pool age distribution
        pool_age_stats = {}
        if self.pool:
            ages = [(now - paper.published).days for paper in self.pool]
            pool_age_stats = {
                'min_age_days': min(ages),
                'max_age_days': max(ages),
                'avg_age_days': sum(ages) / len(ages)
            }
        
        return {
            'enabled': self.enabled,
            'pool_size': len(self.pool),
            'candidates_count': len(self.candidates),
            'blacklist_size': len(self.blacklist),
            'posted_total': self.posted_total,
            'posts_today': len(self.posted_today),
            'max_posts_per_day': self.max_posts_per_day,
            'target_channel': self.target_channel,
            'pool_retention_days': self.pool_retention_days,
            'max_pool_size': self.max_pool_size,
            'max_candidates': self.max_candidates,
            'pool_age_stats': pool_age_stats,
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

    async def _assess_paper_accessibility(self, paper) -> str:
        """
        Assess the accessibility of a paper using BAML WritePaperSummary.
        
        Args:
            paper: ArxivPaper object to assess
            
        Returns:
            Accessibility rating: "low", "medium", "high", or "unknown" if assessment fails
        """
        try:
            from baml_client.sync_client import b
            
            logger.debug(f"Assessing accessibility for paper: {paper.title[:50]}...")
            
            # Try to crawl the full paper content first
            try:
                crawler = getattr(self.bot, 'crawler', None)
                if crawler:
                    from crawl4ai import CrawlerRunConfig
                    
                    # Try the HTML version first (better for parsing)
                    html_url = paper.arxiv_url.replace('/abs/', '/html/')
                    
                    logger.debug(f"Attempting to crawl ArXiv HTML for accessibility assessment: {html_url}")
                    await crawler.start()
                    result = await crawler.arun(url=html_url, config=CrawlerRunConfig(
                        exclude_external_images=False,
                        wait_for_images=True
                    ))
                    
                    if result and hasattr(result, 'markdown') and result.markdown:
                        logger.debug(f"Successfully crawled paper content for accessibility assessment ({len(result.markdown)} chars)")
                        
                        # Parse the full paper content
                        parsed_paper = b.ParsePaper(result.markdown)
                        
                        # Get paper summary with accessibility assessment
                        paper_summary = b.WritePaperSummary(parsed_paper)
                        
                        accessibility = paper_summary.accessibility
                        logger.debug(f"Accessibility assessment from full content: {accessibility}")
                        return accessibility
                    else:
                        logger.debug(f"Failed to crawl paper content for accessibility assessment from {html_url}")
                else:
                    logger.debug("No crawler available for accessibility assessment")
                    
            except Exception as crawl_error:
                logger.debug(f"Crawling failed for accessibility assessment {paper.arxiv_url}: {crawl_error}")
            
            # Fallback: assess accessibility based on abstract only
            logger.debug("Falling back to accessibility assessment from abstract...")
            
            # Create a minimal Paper object from the abstract
            from baml_client.types import Paper, Paragraph
            
            minimal_paper = Paper(
                title=paper.title,
                body=[Paragraph(text=paper.abstract)],
                figures=[],
                authors=paper.authors,
                date=paper.published.strftime('%Y-%m-%d'),
                tags=paper.categories,
                purpose="Research paper accessibility assessment"
            )
            
            # Get accessibility assessment
            paper_summary = b.WritePaperSummary(minimal_paper)
            accessibility = paper_summary.accessibility
            
            logger.debug(f"Accessibility assessment from abstract: {accessibility}")
            return accessibility
            
        except Exception as e:
            logger.warning(f"Failed to assess accessibility for paper '{paper.title[:50]}...': {e}")
            return "unknown" 