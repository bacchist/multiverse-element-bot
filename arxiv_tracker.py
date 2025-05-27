#!/usr/bin/env python3
"""
ArXiv AI Paper Tracker with Altmetric Integration

A standalone module for fetching and ranking AI papers from arXiv by popularity.
Designed to be completely optional and not interfere with core bot functionality.
"""

import asyncio
import aiohttp
import json
import logging
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import quote_plus
import time

# Configure logging for this module
logger = logging.getLogger(__name__)

@dataclass
class ArxivPaper:
    """Represents an arXiv paper with metadata and popularity metrics."""
    arxiv_id: str
    title: str
    authors: List[str]
    abstract: str
    categories: List[str]
    published: datetime
    updated: datetime
    pdf_url: str
    arxiv_url: str
    doi: Optional[str] = None
    altmetric_score: Optional[float] = None
    altmetric_data: Optional[Dict[str, Any]] = None
    priority_score: float = field(default=0.0)

    def __post_init__(self):
        """Calculate priority score based on available metrics."""
        self.priority_score = self._calculate_priority()

    def _calculate_priority(self) -> float:
        """Calculate a priority score for ranking papers."""
        score = 0.0
        
        # Base score from Altmetric (heavily weighted using (score + 1)² formula)
        if self.altmetric_score and self.altmetric_score > 0:
            # Use (altmetric_score + 1)² for exponential weighting
            # This heavily favors papers with any Altmetric data
            altmetric_weight = (self.altmetric_score + 1) ** 2
            score += altmetric_weight
            
            # Additional bonus for very high scores
            if self.altmetric_score >= 10:
                score += 100  # Extra boost for viral papers
            elif self.altmetric_score >= 5:
                score += 50   # Boost for highly trending papers
        
        # Recency bonus (reduced impact compared to Altmetric)
        now = datetime.now(timezone.utc)
        hours_old = (now - self.published).total_seconds() / 3600
        if hours_old < 24:
            score += 25 * (1 - hours_old / 24)  # Reduced from 50
        elif hours_old < 48:
            # Smaller bonus for papers 24-48 hours old
            score += 12 * (1 - (hours_old - 24) / 24)  # Reduced from 25
        
        # Category bonus for popular AI categories (reduced impact)
        popular_categories = {'cs.AI': 15, 'cs.LG': 12, 'cs.CL': 10, 'cs.CV': 10, 'cs.NE': 8}
        for category in self.categories:
            if category in popular_categories:
                score += popular_categories[category]
                break
        
        # Bonus for papers with social media engagement (from Altmetric data)
        if self.altmetric_data:
            # Twitter engagement bonus (reduced caps)
            tweets = self.altmetric_data.get('cited_by_tweeters_count', 0)
            if tweets > 0:
                score += min(tweets * 1.5, 20)  # Reduced from 2x and cap of 30
            
            # Reddit engagement bonus (reduced caps)
            reddit = self.altmetric_data.get('cited_by_rdts_count', 0)
            if reddit > 0:
                score += min(reddit * 3, 15)  # Reduced from 5x and cap of 25
            
            # News coverage bonus (reduced caps)
            news = self.altmetric_data.get('cited_by_feeds_count', 0)
            if news > 0:
                score += min(news * 6, 30)  # Reduced from 10x and cap of 50
        
        return score


class ArxivAltmetricTracker:
    """Tracks AI papers from arXiv and enriches them with Altmetric popularity data."""
    
    def __init__(self, rate_limit_delay: float = 1.0):
        """
        Initialize the tracker.
        
        Args:
            rate_limit_delay: Delay between API requests to respect rate limits
        """
        self.rate_limit_delay = rate_limit_delay
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Default AI categories to search
        self.default_categories = [
            'cs.AI',    # Artificial Intelligence
            'cs.LG',    # Machine Learning
            'cs.CL',    # Computation and Language (NLP)
            'cs.CV',    # Computer Vision
            'cs.NE',    # Neural and Evolutionary Computing
            'stat.ML'   # Machine Learning (Statistics)
        ]

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def fetch_recent_papers(
        self, 
        days_back: int = 3, 
        max_results: int = 50,
        categories: Optional[List[str]] = None
    ) -> List[ArxivPaper]:
        """
        Fetch recent AI papers from arXiv.
        
        Args:
            days_back: Number of days to look back
            max_results: Maximum number of papers to fetch
            categories: List of arXiv categories to search (defaults to AI categories)
            
        Returns:
            List of ArxivPaper objects
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        categories = categories or self.default_categories
        
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        # Build search query
        category_query = " OR ".join([f"cat:{cat}" for cat in categories])
        date_query = f"submittedDate:[{start_date.strftime('%Y%m%d')}* TO {end_date.strftime('%Y%m%d')}*]"
        search_query = f"({category_query}) AND {date_query}"
        
        logger.info(f"Searching arXiv for papers in last {days_back} days...")
        logger.debug(f"Query: {search_query}")
        
        # Fetch from arXiv API
        url = "http://export.arxiv.org/api/query"
        params = {
            'search_query': search_query,
            'start': 0,
            'max_results': max_results,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"arXiv API error: {response.status}")
                    return []
                
                content = await response.text()
                papers = self._parse_arxiv_response(content)
                logger.info(f"Found {len(papers)} papers from arXiv")
                return papers
                
        except Exception as e:
            logger.error(f"Error fetching from arXiv: {e}")
            return []

    def _parse_arxiv_response(self, xml_content: str) -> List[ArxivPaper]:
        """Parse arXiv API XML response into ArxivPaper objects."""
        papers = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Handle namespaces
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            for entry in root.findall('atom:entry', namespaces):
                try:
                    # Extract basic info with better error handling
                    title_elem = entry.find('atom:title', namespaces)
                    abstract_elem = entry.find('atom:summary', namespaces)
                    id_elem = entry.find('atom:id', namespaces)
                    published_elem = entry.find('atom:published', namespaces)
                    updated_elem = entry.find('atom:updated', namespaces)
                    
                    # Check for required elements and their text content
                    if (title_elem is None or not title_elem.text or
                        abstract_elem is None or not abstract_elem.text or
                        id_elem is None or not id_elem.text or
                        published_elem is None or not published_elem.text or
                        updated_elem is None or not updated_elem.text):
                        continue  # Skip this entry silently
                    
                    title = title_elem.text.strip()
                    abstract = abstract_elem.text.strip()
                    
                    # Extract arXiv ID from the ID URL
                    id_url = id_elem.text
                    arxiv_id_full = id_url.split('/')[-1]
                    
                    # Remove version number for Altmetric API compatibility (e.g., 2505.20245v1 -> 2505.20245)
                    # Keep the full ID for URLs but store base ID for Altmetric lookups
                    arxiv_id_base = arxiv_id_full.split('v')[0] if 'v' in arxiv_id_full else arxiv_id_full  # Remove version for Altmetric
                    
                    # Extract authors
                    authors = []
                    for author in entry.findall('atom:author', namespaces):
                        name = author.find('atom:name', namespaces)
                        if name is not None and name.text:
                            authors.append(name.text)
                    
                    # Skip if no authors found
                    if not authors:
                        continue
                    
                    # Extract categories
                    categories = []
                    for category in entry.findall('atom:category', namespaces):
                        term = category.get('term')
                        if term:
                            categories.append(term)
                    
                    # Skip if no categories found
                    if not categories:
                        continue
                    
                    # Extract dates
                    published_str = published_elem.text
                    updated_str = updated_elem.text
                    
                    try:
                        published = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                        updated = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                    except ValueError:
                        continue  # Skip if date parsing fails
                    
                    # Extract DOI if available
                    doi = None
                    doi_elem = entry.find('arxiv:doi', namespaces)
                    if doi_elem is not None and doi_elem.text:
                        doi = doi_elem.text
                    
                    # Build URLs
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id_full}.pdf"
                    arxiv_url = f"https://arxiv.org/abs/{arxiv_id_full}"
                    
                    paper = ArxivPaper(
                        arxiv_id=arxiv_id_base,
                        title=title,
                        authors=authors,
                        abstract=abstract,
                        categories=categories,
                        published=published,
                        updated=updated,
                        pdf_url=pdf_url,
                        arxiv_url=arxiv_url,
                        doi=doi
                    )
                    
                    papers.append(paper)
                    
                except Exception as e:
                    logger.warning(f"Error parsing paper entry: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing arXiv XML: {e}")
            
        return papers

    async def enrich_with_altmetric(self, papers: List[ArxivPaper]) -> List[ArxivPaper]:
        """
        Enrich papers with Altmetric popularity data.
        
        Args:
            papers: List of ArxivPaper objects to enrich
            
        Returns:
            List of papers with Altmetric data added
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        logger.info(f"Enriching {len(papers)} papers with Altmetric data...")
        
        for i, paper in enumerate(papers):
            try:
                # Try DOI first, then arXiv ID
                altmetric_data = None
                if paper.doi:
                    altmetric_data = await self._fetch_altmetric_by_doi(paper.doi)
                
                if not altmetric_data:
                    altmetric_data = await self._fetch_altmetric_by_arxiv(paper.arxiv_id)
                
                if altmetric_data:
                    paper.altmetric_score = altmetric_data.get('score', 0)
                    paper.altmetric_data = altmetric_data
                    logger.debug(f"Found Altmetric data for {paper.arxiv_id}: score={paper.altmetric_score}")
                else:
                    paper.altmetric_score = 0
                    logger.debug(f"No Altmetric data for {paper.arxiv_id}")
                
                # Recalculate priority score with new Altmetric data
                paper.priority_score = paper._calculate_priority()
                
                # Rate limiting
                if i < len(papers) - 1:
                    await asyncio.sleep(self.rate_limit_delay)
                    
            except Exception as e:
                logger.warning(f"Error fetching Altmetric for {paper.arxiv_id}: {e}")
                paper.altmetric_score = 0
                continue
        
        logger.info("Altmetric enrichment complete")
        return papers

    async def _fetch_altmetric_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Fetch Altmetric data by DOI."""
        url = f"https://api.altmetric.com/v1/doi/{quote_plus(doi)}"
        return await self._fetch_altmetric_data(url)

    async def _fetch_altmetric_by_arxiv(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """Fetch Altmetric data by arXiv ID."""
        url = f"https://api.altmetric.com/v1/arxiv/{arxiv_id}"
        return await self._fetch_altmetric_data(url)

    async def _fetch_altmetric_data(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch data from Altmetric API."""
        try:
            if self.session is None:
                return None
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    # No Altmetric data available
                    return None
                else:
                    logger.warning(f"Altmetric API error {response.status} for {url}")
                    return None
        except Exception as e:
            logger.warning(f"Error fetching Altmetric data from {url}: {e}")
            return None

    def rank_papers_by_popularity(self, papers: List[ArxivPaper]) -> List[ArxivPaper]:
        """
        Rank papers by popularity using priority score.
        
        Args:
            papers: List of papers to rank
            
        Returns:
            List of papers sorted by popularity (highest first)
        """
        return sorted(papers, key=lambda p: p.priority_score, reverse=True)

    async def get_trending_papers(
        self, 
        days_back: int = 3, 
        count: int = 5,
        categories: Optional[List[str]] = None,
        include_altmetric: bool = True
    ) -> List[ArxivPaper]:
        """
        Get trending AI papers - convenience method that combines all steps.
        
        Args:
            days_back: Number of days to look back
            count: Number of top papers to return
            categories: List of arXiv categories to search
            include_altmetric: Whether to fetch Altmetric data
            
        Returns:
            List of top trending papers
        """
        try:
            # Fetch recent papers
            papers = await self.fetch_recent_papers(
                days_back=days_back,
                max_results=min(50, count * 3),  # Fetch more to have good selection
                categories=categories
            )
            
            if not papers:
                return []
            
            # Enrich with Altmetric data if requested
            if include_altmetric:
                papers = await self.enrich_with_altmetric(papers)
            
            # Rank and return top papers
            ranked_papers = self.rank_papers_by_popularity(papers)
            return ranked_papers[:count]
            
        except Exception as e:
            logger.error(f"Error getting trending papers: {e}")
            return []


# CLI functionality for standalone usage
async def main():
    """Main function for CLI usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ArXiv AI Paper Tracker with Altmetric Ranking")
    parser.add_argument('--days', type=int, default=3, help='Days to look back (default: 3)')
    parser.add_argument('--count', type=int, default=5, help='Number of papers to display (default: 5)')
    parser.add_argument('--max-results', type=int, default=50, help='Max papers to fetch (default: 50)')
    parser.add_argument('--categories', nargs='+', help='arXiv categories to search')
    parser.add_argument('--no-altmetric', action='store_true', help='Skip Altmetric data (faster)')
    parser.add_argument('--format', choices=['terminal', 'markdown', 'json'], default='terminal', help='Output format')
    parser.add_argument('--output', help='Save results to file (JSON format)')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        async with ArxivAltmetricTracker() as tracker:
            papers = await tracker.get_trending_papers(
                days_back=args.days,
                count=args.count,
                categories=args.categories,
                include_altmetric=not args.no_altmetric
            )
            
            if not papers:
                print("No papers found matching criteria.")
                return 1
            
            # Display results
            if args.format == 'json':
                print(json.dumps([{
                    'arxiv_id': p.arxiv_id,
                    'title': p.title,
                    'authors': p.authors,
                    'abstract': p.abstract,
                    'categories': p.categories,
                    'published': p.published.isoformat(),
                    'altmetric_score': p.altmetric_score,
                    'priority_score': p.priority_score,
                    'arxiv_url': p.arxiv_url,
                    'pdf_url': p.pdf_url
                } for p in papers], indent=2))
            else:
                # Terminal format
                print(f"\n🤖 Top {len(papers)} Trending AI Papers (Last {args.days} days)")
                print("=" * 80)
                
                for i, paper in enumerate(papers, 1):
                    print(f"\n#{i}. {paper.title}")
                    print(f"Authors: {', '.join(paper.authors[:3])}")
                    print(f"Published: {paper.published.strftime('%Y-%m-%d')}")
                    print(f"Categories: {', '.join(paper.categories[:3])}")
                    if paper.altmetric_score:
                        print(f"Altmetric Score: {paper.altmetric_score:.1f}")
                    print(f"Priority Score: {paper.priority_score:.1f}")
                    print(f"URL: {paper.arxiv_url}")
                    print("-" * 80)
            
            # Save to file if requested
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump([{
                        'arxiv_id': p.arxiv_id,
                        'title': p.title,
                        'authors': p.authors,
                        'abstract': p.abstract,
                        'categories': p.categories,
                        'published': p.published.isoformat(),
                        'altmetric_score': p.altmetric_score,
                        'priority_score': p.priority_score,
                        'arxiv_url': p.arxiv_url,
                        'pdf_url': p.pdf_url
                    } for p in papers], f, indent=2)
                print(f"\nResults saved to {args.output}")
            
            return 0
            
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main()) 