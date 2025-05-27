#!/usr/bin/env python3
"""
ArXiv Auto Poster for Matrix Bot

Automatically discovers trending AI papers and posts them to Matrix channels
with AI-generated comments. Includes queue management and duplicate prevention.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set
import hashlib
from dataclasses import dataclass, asdict
import niobot

from arxiv_tracker import ArxivAltmetricTracker, ArxivPaper
from baml_client.sync_client import b

@dataclass
class QueuedPaper:
    """Represents a paper in the posting queue."""
    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    published: str  # ISO format
    arxiv_url: str
    pdf_url: str
    altmetric_score: float
    altmetric_data: Optional[Dict]
    discovered_at: str  # ISO format
    priority_score: float  # Combined ranking score
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_arxiv_paper(cls, paper: ArxivPaper, priority_score: float) -> 'QueuedPaper':
        """Create from ArxivPaper object."""
        return cls(
            arxiv_id=paper.arxiv_id.split('v')[0],  # Clean ID without version
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            categories=paper.categories,
            published=paper.published.isoformat(),
            arxiv_url=paper.arxiv_url,
            pdf_url=paper.pdf_url,
            altmetric_score=paper.altmetric_score or 0.0,
            altmetric_data=paper.altmetric_data,
            discovered_at=datetime.now().isoformat(),
            priority_score=priority_score
        )

class ArxivAutoPoster:
    """Manages automatic discovery and posting of AI papers."""
    
    def __init__(self, bot: niobot.NioBot):
        self.bot = bot
        self.tracker = ArxivAltmetricTracker()
        
        # Configuration
        self.target_channel = "#ai-papers:themultiverse.school"
        self.queue_file = Path("store/arxiv_queue.json")
        self.posted_file = Path("store/arxiv_posted.json")
        self.discovery_interval = timedelta(days=1)  # Run discovery daily
        self.posting_interval = timedelta(hours=3)   # Post every 3 hours
        self.max_posts_per_day = 5  # Limit posts per day
        
        # Ensure store directory exists
        self.queue_file.parent.mkdir(exist_ok=True)
        
        # State
        self.queue: List[QueuedPaper] = []
        self.posted_papers: Set[str] = set()  # Set of posted arxiv_ids
        self.last_discovery: Optional[datetime] = None
        self.last_posting: Optional[datetime] = None
        self.posts_today = 0
        self.last_post_date: Optional[str] = None
        
        # Load existing data
        self._load_queue()
        self._load_posted_papers()
    
    def _load_queue(self):
        """Load the posting queue from file."""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.queue = [QueuedPaper(**item) for item in data.get('papers', [])]
                    
                    # Load metadata
                    metadata = data.get('metadata', {})
                    if metadata.get('last_discovery'):
                        self.last_discovery = datetime.fromisoformat(metadata['last_discovery'])
                    if metadata.get('last_posting'):
                        self.last_posting = datetime.fromisoformat(metadata['last_posting'])
                    self.posts_today = metadata.get('posts_today', 0)
                    self.last_post_date = metadata.get('last_post_date')
                    
                print(f"📥 Loaded {len(self.queue)} papers from queue")
            except Exception as e:
                print(f"❌ Error loading queue: {e}")
                self.queue = []
    
    def _save_queue(self):
        """Save the posting queue to file."""
        try:
            data = {
                'metadata': {
                    'last_discovery': self.last_discovery.isoformat() if self.last_discovery else None,
                    'last_posting': self.last_posting.isoformat() if self.last_posting else None,
                    'posts_today': self.posts_today,
                    'last_post_date': self.last_post_date,
                    'updated_at': datetime.now().isoformat()
                },
                'papers': [paper.to_dict() for paper in self.queue]
            }
            
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"❌ Error saving queue: {e}")
    
    def _load_posted_papers(self):
        """Load the list of already posted papers."""
        if self.posted_file.exists():
            try:
                with open(self.posted_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.posted_papers = set(data.get('posted_arxiv_ids', []))
                print(f"📥 Loaded {len(self.posted_papers)} posted papers")
            except Exception as e:
                print(f"❌ Error loading posted papers: {e}")
                self.posted_papers = set()
    
    def _save_posted_papers(self):
        """Save the list of posted papers."""
        try:
            data = {
                'posted_arxiv_ids': list(self.posted_papers),
                'updated_at': datetime.now().isoformat(),
                'total_posted': len(self.posted_papers)
            }
            
            with open(self.posted_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"❌ Error saving posted papers: {e}")
    
    def _reset_daily_counter(self):
        """Reset daily post counter if it's a new day."""
        today = datetime.now().strftime('%Y-%m-%d')
        if self.last_post_date != today:
            self.posts_today = 0
            self.last_post_date = today
    
    def _calculate_priority_score(self, paper: ArxivPaper) -> float:
        """Calculate priority score for ranking papers."""
        score = 0.0
        
        # Altmetric score (primary factor)
        if paper.altmetric_score:
            score += paper.altmetric_score * 10
        
        # Recency bonus (newer papers get slight boost)
        days_old = (datetime.now(paper.published.tzinfo) - paper.published).days
        if days_old <= 1:
            score += 5
        elif days_old <= 3:
            score += 2
        
        # Category bonus for core AI/LLM topics
        high_priority_cats = ['cs.AI', 'cs.LG', 'cs.CL']
        medium_priority_cats = ['cs.CV', 'cs.NE', 'stat.ML']
        
        if any(cat in paper.categories for cat in high_priority_cats):
            score += 3
        elif any(cat in paper.categories for cat in medium_priority_cats):
            score += 1
        
        # Title/abstract keyword bonus for LLM-related papers
        llm_keywords = [
            'llm', 'large language model', 'gpt', 'transformer', 'bert', 'attention',
            'neural network', 'deep learning', 'machine learning', 'artificial intelligence',
            'natural language processing', 'nlp', 'generative', 'chatbot', 'reasoning'
        ]
        
        text_to_check = (paper.title + ' ' + paper.abstract).lower()
        keyword_matches = sum(1 for keyword in llm_keywords if keyword in text_to_check)
        score += keyword_matches * 0.5
        
        return score
    
    async def discover_papers(self, days_back: int = 3, max_results: int = 50) -> int:
        """Discover new trending papers and add them to the queue."""
        print(f"🔍 Discovering AI papers from last {days_back} days...")
        
        try:
            # Fetch recent papers
            papers = await self.tracker.fetch_recent_papers(
                days_back=days_back,
                max_results=max_results
            )
            
            if not papers:
                print("❌ No papers found")
                return 0
            
            # Enrich with Altmetric data
            papers = await self.tracker.enrich_with_altmetric(papers)
            
            # Filter and queue new papers
            new_papers = 0
            for paper in papers:
                arxiv_id_clean = paper.arxiv_id.split('v')[0]
                
                # Skip if already posted or queued
                if arxiv_id_clean in self.posted_papers:
                    continue
                
                if any(q.arxiv_id == arxiv_id_clean for q in self.queue):
                    continue
                
                # Calculate priority and add to queue
                priority_score = self._calculate_priority_score(paper)
                
                # Only queue papers with decent scores
                if priority_score >= 1.0:
                    queued_paper = QueuedPaper.from_arxiv_paper(paper, priority_score)
                    self.queue.append(queued_paper)
                    new_papers += 1
            
            # Sort queue by priority score (highest first)
            self.queue.sort(key=lambda p: p.priority_score, reverse=True)
            
            # Update discovery time
            self.last_discovery = datetime.now()
            self._save_queue()
            
            print(f"✅ Discovered {new_papers} new papers, queue now has {len(self.queue)} papers")
            return new_papers
            
        except Exception as e:
            print(f"❌ Error during discovery: {e}")
            return 0
    
    async def generate_comment(self, paper: QueuedPaper) -> str:
        """Generate an AI comment for the paper."""
        try:
            # Prepare paper info for the AI
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += f" et al. ({len(paper.authors)} authors)"
            
            categories_str = ", ".join([cat for cat in paper.categories if cat.startswith(('cs.', 'stat.'))][:3])
            
            # Altmetric info
            altmetric_info = ""
            if paper.altmetric_score > 0:
                altmetric_info = f"Altmetric score: {paper.altmetric_score:.1f}"
                if paper.altmetric_data:
                    mentions = []
                    if paper.altmetric_data.get('cited_by_tweeters_count', 0) > 0:
                        mentions.append(f"{paper.altmetric_data['cited_by_tweeters_count']} tweets")
                    if paper.altmetric_data.get('cited_by_posts_count', 0) > 0:
                        mentions.append(f"{paper.altmetric_data['cited_by_posts_count']} posts")
                    if mentions:
                        altmetric_info += f" ({', '.join(mentions)})"
            
            # Use the same AI system as the bot for generating comments
            comment = b.GeneratePaperComment(
                title=paper.title,
                authors=authors_str,
                abstract=paper.abstract[:500] + "..." if len(paper.abstract) > 500 else paper.abstract,
                categories=categories_str,
                altmetric_info=altmetric_info,
                context="This is a trending AI/ML paper from arXiv that's being shared in an AI research community channel."
            )
            
            return comment.comment
            
        except Exception as e:
            print(f"❌ Error generating comment: {e}")
            # Fallback comment
            return f"🤖 Trending AI paper with Altmetric score {paper.altmetric_score:.1f}! Worth checking out."
    
    async def post_next_paper(self) -> bool:
        """Post the next paper from the queue to the target channel."""
        if not self.queue:
            print("📭 Queue is empty, nothing to post")
            return False
        
        # Check daily limit
        self._reset_daily_counter()
        if self.posts_today >= self.max_posts_per_day:
            print(f"📊 Daily limit reached ({self.posts_today}/{self.max_posts_per_day})")
            return False
        
        # Get the highest priority paper
        paper = self.queue.pop(0)
        
        try:
            # Generate AI comment
            print(f"🤖 Generating comment for: {paper.title[:50]}...")
            comment = await self.generate_comment(paper)
            
            # Format the post
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += f" et al. ({len(paper.authors)} total)"
            
            # Altmetric info
            altmetric_info = ""
            if paper.altmetric_score > 0:
                altmetric_info = f"📊 Altmetric: {paper.altmetric_score:.1f}"
                if paper.altmetric_data:
                    mentions = []
                    if paper.altmetric_data.get('cited_by_tweeters_count', 0) > 0:
                        mentions.append(f"{paper.altmetric_data['cited_by_tweeters_count']} tweets")
                    if paper.altmetric_data.get('cited_by_posts_count', 0) > 0:
                        mentions.append(f"{paper.altmetric_data['cited_by_posts_count']} posts")
                    if paper.altmetric_data.get('cited_by_rdts_count', 0) > 0:
                        mentions.append(f"{paper.altmetric_data['cited_by_rdts_count']} Reddit")
                    
                    if mentions:
                        altmetric_info += f" ({', '.join(mentions)})"
            
            # Categories
            main_categories = [cat for cat in paper.categories if cat.startswith(('cs.', 'stat.'))][:3]
            categories_str = ", ".join(main_categories)
            
            # Create the message
            message = f"""🤖 **{comment}**

**{paper.title}**

👥 {authors_str}
📅 {datetime.fromisoformat(paper.published).strftime('%Y-%m-%d')} | 🏷️ {categories_str}
{altmetric_info}

🔗 [arXiv]({paper.arxiv_url}) | [PDF]({paper.pdf_url})"""
            
            # Post to the channel
            print(f"📤 Posting to {self.target_channel}: {paper.title[:50]}...")
            
            # Send the message using the simpler API
            try:
                # Try to resolve the room alias to get room ID
                room_id = None
                try:
                    room_response = await self.bot.room_resolve_alias(self.target_channel)
                    # Check if the response is a success response (has room_id attribute)
                    if hasattr(room_response, 'room_id') and room_response.room_id:
                        room_id = room_response.room_id
                except Exception:
                    # Resolution failed, try to find the room in joined rooms
                    pass
                
                # If resolution fails, try to find the room in joined rooms
                if not room_id:
                    for rid, room_obj in self.bot.rooms.items():
                        if hasattr(room_obj, 'canonical_alias') and room_obj.canonical_alias == self.target_channel:
                            room_id = rid
                            break
                    
                    if not room_id:
                        print(f"❌ Could not resolve room: {self.target_channel}")
                        # Put paper back in queue
                        self.queue.insert(0, paper)
                        return False
                
                # Send the message using the room ID
                response = await self.bot.room_send(
                    room_id=room_id,
                    message_type="m.room.message",
                    content={
                        "msgtype": "m.text",
                        "body": message,
                        "format": "org.matrix.custom.html",
                        "formatted_body": message
                    }
                )
                
                # Check if the send was successful
                if hasattr(response, 'event_id'):
                    # Mark as posted
                    self.posted_papers.add(paper.arxiv_id)
                    self.posts_today += 1
                    self.last_posting = datetime.now()
                    
                    # Save state
                    self._save_queue()
                    self._save_posted_papers()
                    
                    print(f"✅ Posted successfully! ({self.posts_today}/{self.max_posts_per_day} today)")
                    return True
                else:
                    print(f"❌ Failed to send message: {response}")
                    # Put paper back in queue
                    self.queue.insert(0, paper)
                    return False
                
            except Exception as e:
                print(f"❌ Error sending message: {e}")
                # Put paper back in queue
                self.queue.insert(0, paper)
                return False
                
        except Exception as e:
            print(f"❌ Error posting paper: {e}")
            # Put paper back in queue
            self.queue.insert(0, paper)
            return False
    
    async def run_discovery_cycle(self):
        """Run a discovery cycle if it's time."""
        now = datetime.now()
        
        # Check if it's time for discovery
        if (self.last_discovery is None or 
            now - self.last_discovery >= self.discovery_interval):
            
            print("🔄 Starting discovery cycle...")
            await self.discover_papers()
        else:
            next_discovery = self.last_discovery + self.discovery_interval
            print(f"⏰ Next discovery in {next_discovery - now}")
    
    async def run_posting_cycle(self):
        """Run a posting cycle if it's time."""
        now = datetime.now()
        
        # Check if it's time for posting
        if (self.last_posting is None or 
            now - self.last_posting >= self.posting_interval):
            
            if self.queue:
                print("📤 Starting posting cycle...")
                await self.post_next_paper()
            else:
                print("📭 No papers in queue to post")
        else:
            next_posting = self.last_posting + self.posting_interval
            print(f"⏰ Next posting in {next_posting - now}")
    
    async def run_maintenance_cycle(self):
        """Run both discovery and posting cycles."""
        await self.run_discovery_cycle()
        await self.run_posting_cycle()
    
    def get_status(self) -> Dict:
        """Get current status of the auto poster."""
        self._reset_daily_counter()
        
        return {
            'queue_size': len(self.queue),
            'posted_total': len(self.posted_papers),
            'posts_today': self.posts_today,
            'max_posts_per_day': self.max_posts_per_day,
            'last_discovery': self.last_discovery.isoformat() if self.last_discovery else None,
            'last_posting': self.last_posting.isoformat() if self.last_posting else None,
            'target_channel': self.target_channel,
            'next_discovery': (self.last_discovery + self.discovery_interval).isoformat() if self.last_discovery else 'Now',
            'next_posting': (self.last_posting + self.posting_interval).isoformat() if self.last_posting else 'Now'
        } 