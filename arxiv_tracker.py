#!/usr/bin/env python3
"""
ArXiv AI Paper Tracker with Altmetric Ranking

This script fetches new AI papers from arXiv and ranks them by their
popularity using the Altmetric API.

Categories covered:
- cs.AI (Artificial Intelligence)
- cs.LG (Machine Learning) 
- cs.CL (Computation and Language/NLP)
- cs.CV (Computer Vision)
- cs.NE (Neural and Evolutionary Computing)
- stat.ML (Machine Learning Statistics)

Usage:
    python arxiv_tracker.py --days 7 --count 10 --output papers.json
    python arxiv_tracker.py --help
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import json
import time
import argparse
import sys
from dataclasses import dataclass
from urllib.parse import quote
import re

@dataclass
class ArxivPaper:
    """Represents an arXiv paper with metadata."""
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
    altmetric_data: Optional[Dict] = None

class ArxivAltmetricTracker:
    """Fetches arXiv papers and enriches them with Altmetric data."""
    
    def __init__(self):
        self.arxiv_base_url = "http://export.arxiv.org/api/query"
        self.altmetric_base_url = "https://api.altmetric.com/v1"
        
        # AI-related categories on arXiv
        self.ai_categories = [
            "cs.AI",    # Artificial Intelligence
            "cs.LG",    # Machine Learning
            "cs.CL",    # Computation and Language (NLP)
            "cs.CV",    # Computer Vision and Pattern Recognition
            "cs.NE",    # Neural and Evolutionary Computing
            "stat.ML",  # Machine Learning (Statistics)
        ]
        
        # Rate limiting
        self.arxiv_delay = 3  # seconds between arXiv requests
        self.altmetric_delay = 1  # seconds between Altmetric requests
    
    async def fetch_recent_papers(self, days_back: int = 7, max_results: int = 100) -> List[ArxivPaper]:
        """
        Fetch recent papers from arXiv in AI categories.
        
        Args:
            days_back: How many days back to search
            max_results: Maximum number of papers to fetch
            
        Returns:
            List of ArxivPaper objects
        """
        # Build search query for AI categories
        category_query = " OR ".join([f"cat:{cat}" for cat in self.ai_categories])
        
        # Date range for recent papers
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # arXiv query parameters
        params = {
            'search_query': f"({category_query}) AND submittedDate:[{start_date.strftime('%Y%m%d')}* TO {end_date.strftime('%Y%m%d')}*]",
            'start': 0,
            'max_results': max_results,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }
        
        print(f"Fetching papers from arXiv (last {days_back} days)...")
        
        async with aiohttp.ClientSession() as session:
            papers = await self._fetch_arxiv_papers(session, params)
            
        print(f"Found {len(papers)} papers")
        return papers
    
    async def _fetch_arxiv_papers(self, session: aiohttp.ClientSession, params: Dict) -> List[ArxivPaper]:
        """Fetch papers from arXiv API."""
        try:
            async with session.get(self.arxiv_base_url, params=params) as response:
                if response.status != 200:
                    print(f"arXiv API error: {response.status}")
                    return []
                
                xml_content = await response.text()
                return self._parse_arxiv_xml(xml_content)
                
        except Exception as e:
            print(f"Error fetching from arXiv: {e}")
            return []
    
    def _parse_arxiv_xml(self, xml_content: str) -> List[ArxivPaper]:
        """Parse arXiv XML response into ArxivPaper objects."""
        papers = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Define namespaces
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            for entry in root.findall('atom:entry', namespaces):
                try:
                    # Extract basic metadata
                    title_elem = entry.find('atom:title', namespaces)
                    if title_elem is None or title_elem.text is None:
                        continue
                    title = title_elem.text.strip()
                    title = re.sub(r'\s+', ' ', title)  # Clean up whitespace
                    
                    # Extract arXiv ID from the ID URL
                    id_elem = entry.find('atom:id', namespaces)
                    if id_elem is None or id_elem.text is None:
                        continue
                    id_url = id_elem.text
                    arxiv_id = id_url.split('/')[-1]
                    
                    # Authors
                    authors = []
                    for author in entry.findall('atom:author', namespaces):
                        name_elem = author.find('atom:name', namespaces)
                        if name_elem is not None and name_elem.text is not None:
                            authors.append(name_elem.text)
                    
                    # Abstract
                    abstract_elem = entry.find('atom:summary', namespaces)
                    if abstract_elem is None or abstract_elem.text is None:
                        continue
                    abstract = abstract_elem.text.strip()
                    abstract = re.sub(r'\s+', ' ', abstract)  # Clean up whitespace
                    
                    # Categories
                    categories = []
                    for category in entry.findall('atom:category', namespaces):
                        term = category.get('term')
                        if term:
                            categories.append(term)
                    
                    # Dates
                    published_elem = entry.find('atom:published', namespaces)
                    updated_elem = entry.find('atom:updated', namespaces)
                    
                    if published_elem is None or published_elem.text is None:
                        continue
                    if updated_elem is None or updated_elem.text is None:
                        continue
                        
                    published_str = published_elem.text
                    updated_str = updated_elem.text
                    
                    published = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                    updated = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                    
                    # URLs
                    pdf_url = None
                    arxiv_url = None
                    
                    for link in entry.findall('atom:link', namespaces):
                        if link.get('type') == 'application/pdf':
                            pdf_url = link.get('href')
                        elif link.get('rel') == 'alternate':
                            arxiv_url = link.get('href')
                    
                    # Ensure we have required URLs
                    if pdf_url is None or arxiv_url is None:
                        continue
                    
                    # DOI (if available)
                    doi = None
                    doi_element = entry.find('arxiv:doi', namespaces)
                    if doi_element is not None:
                        doi = doi_element.text
                    
                    paper = ArxivPaper(
                        arxiv_id=arxiv_id,
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
                    print(f"Error parsing paper entry: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error parsing arXiv XML: {e}")
            
        return papers
    
    async def enrich_with_altmetric(self, papers: List[ArxivPaper]) -> List[ArxivPaper]:
        """
        Enrich papers with Altmetric data.
        
        Args:
            papers: List of ArxivPaper objects
            
        Returns:
            Papers enriched with Altmetric scores
        """
        print("Fetching Altmetric data...")
        
        async with aiohttp.ClientSession() as session:
            for i, paper in enumerate(papers):
                try:
                    altmetric_data = await self._fetch_altmetric_data(session, paper)
                    if altmetric_data:
                        paper.altmetric_data = altmetric_data
                        paper.altmetric_score = altmetric_data.get('score', 0)
                    else:
                        paper.altmetric_score = 0
                    
                    # Rate limiting
                    if i < len(papers) - 1:
                        await asyncio.sleep(self.altmetric_delay)
                        
                except Exception as e:
                    print(f"Error fetching Altmetric data for {paper.arxiv_id}: {e}")
                    paper.altmetric_score = 0
                    continue
        
        return papers
    
    async def _fetch_altmetric_data(self, session: aiohttp.ClientSession, paper: ArxivPaper) -> Optional[Dict]:
        """Fetch Altmetric data for a single paper."""
        # Try different identifiers
        identifiers = []
        
        # Try DOI first (most reliable)
        if paper.doi:
            identifiers.append(('doi', paper.doi))
        
        # Try arXiv ID (remove version number for Altmetric API)
        arxiv_id_clean = paper.arxiv_id.split('v')[0]  # Remove version (e.g., 2505.20156v1 -> 2505.20156)
        identifiers.append(('arxiv', arxiv_id_clean))
        
        for id_type, identifier in identifiers:
            try:
                url = f"{self.altmetric_base_url}/{id_type}/{quote(identifier)}"
                
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    elif response.status == 404:
                        # Not found with this identifier, try next
                        continue
                    else:
                        print(f"Altmetric API error for {identifier}: {response.status}")
                        
            except Exception as e:
                print(f"Error fetching Altmetric data for {identifier}: {e}")
                continue
        
        return None
    
    def rank_papers_by_popularity(self, papers: List[ArxivPaper]) -> List[ArxivPaper]:
        """
        Rank papers by Altmetric score and other popularity metrics.
        
        Args:
            papers: List of ArxivPaper objects with Altmetric data
            
        Returns:
            Papers sorted by popularity (highest first)
        """
        def popularity_score(paper: ArxivPaper) -> float:
            """Calculate a composite popularity score."""
            score = 0.0
            
            # Altmetric score (primary factor)
            if paper.altmetric_score:
                score += paper.altmetric_score * 10
            
            # Recency bonus (newer papers get slight boost)
            days_old = (datetime.now(paper.published.tzinfo) - paper.published).days
            if days_old <= 1:
                score += 5  # New papers get a boost
            elif days_old <= 3:
                score += 2
            
            # Category bonus for core AI categories
            core_ai_cats = ['cs.AI', 'cs.LG', 'cs.CL', 'cs.CV']
            if any(cat in paper.categories for cat in core_ai_cats):
                score += 1
            
            return score
        
        # Sort by popularity score (descending)
        ranked_papers = sorted(papers, key=popularity_score, reverse=True)
        
        return ranked_papers
    
    def format_paper_summary(self, paper: ArxivPaper, rank: int) -> str:
        """Format a paper for display."""
        # Truncate title and abstract for readability
        title = paper.title[:100] + "..." if len(paper.title) > 100 else paper.title
        abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
        
        # Format authors (show first 3)
        if len(paper.authors) <= 3:
            authors_str = ", ".join(paper.authors)
        else:
            authors_str = ", ".join(paper.authors[:3]) + f" et al. ({len(paper.authors)} authors)"
        
        # Altmetric info
        altmetric_info = ""
        if paper.altmetric_score and paper.altmetric_score > 0:
            altmetric_info = f" | Altmetric: {paper.altmetric_score:.1f}"
            
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
        main_categories = [cat for cat in paper.categories if cat in self.ai_categories]
        categories_str = ", ".join(main_categories[:3])
        
        summary = f"""**#{rank}. {title}**
👥 {authors_str}
📅 {paper.published.strftime('%Y-%m-%d')} | 🏷️ {categories_str}{altmetric_info}

{abstract}

🔗 [arXiv]({paper.arxiv_url}) | [PDF]({paper.pdf_url})
"""
        
        return summary

async def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Fetch and rank AI papers from arXiv using Altmetric scores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Default: 3 days, top 5 papers
  %(prog)s --days 7 --count 10       # Last 7 days, top 10 papers
  %(prog)s --days 1 --count 20 --output today.json
  %(prog)s --no-altmetric            # Skip Altmetric data (faster)
  %(prog)s --categories cs.AI cs.LG  # Only specific categories
        """
    )
    
    parser.add_argument(
        '--days', '-d', 
        type=int, 
        default=3,
        help='Number of days back to search (default: 3, max: 30)'
    )
    
    parser.add_argument(
        '--count', '-c',
        type=int,
        default=5,
        help='Number of top papers to display (default: 5, max: 50)'
    )
    
    parser.add_argument(
        '--max-results', '-m',
        type=int,
        default=100,
        help='Maximum papers to fetch from arXiv (default: 100)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Save results to JSON file (optional)'
    )
    
    parser.add_argument(
        '--no-altmetric',
        action='store_true',
        help='Skip Altmetric data fetching (faster but no popularity ranking)'
    )
    
    parser.add_argument(
        '--categories',
        nargs='+',
        choices=['cs.AI', 'cs.LG', 'cs.CL', 'cs.CV', 'cs.NE', 'stat.ML'],
        help='Specific categories to search (default: all AI categories)'
    )
    
    parser.add_argument(
        '--format',
        choices=['terminal', 'markdown', 'json'],
        default='terminal',
        help='Output format (default: terminal)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output with debug information'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    args.days = max(1, min(args.days, 30))
    args.count = max(1, min(args.count, 50))
    args.max_results = max(1, min(args.max_results, 500))
    
    # Print header
    print_header(args)
    
    try:
        # Initialize tracker
        tracker = ArxivAltmetricTracker()
        
        # Override categories if specified
        if args.categories:
            tracker.ai_categories = args.categories
            if args.verbose:
                print(f"🔍 Searching categories: {', '.join(args.categories)}")
        
        # Fetch papers
        print(f"📡 Fetching papers from arXiv (last {args.days} days, max {args.max_results} results)...")
        papers = await tracker.fetch_recent_papers(
            days_back=args.days, 
            max_results=args.max_results
        )
        
        if not papers:
            print("❌ No papers found in the specified time range!")
            return 1
        
        print(f"✅ Found {len(papers)} papers")
        
        # Enrich with Altmetric data (unless disabled)
        if not args.no_altmetric:
            print(f"📊 Fetching Altmetric data for {len(papers)} papers...")
            if args.verbose:
                print("   (This may take a while due to API rate limiting)")
            
            papers = await tracker.enrich_with_altmetric(papers)
            
            # Count papers with Altmetric data
            with_altmetric = sum(1 for p in papers if p.altmetric_score and p.altmetric_score > 0)
            print(f"📈 {with_altmetric}/{len(papers)} papers have Altmetric data")
            
            # Rank by popularity
            ranked_papers = tracker.rank_papers_by_popularity(papers)
        else:
            print("⏭️  Skipping Altmetric data (--no-altmetric flag)")
            # Sort by publication date instead
            ranked_papers = sorted(papers, key=lambda p: p.published, reverse=True)
        
        # Get top papers
        top_papers = ranked_papers[:args.count]
        
        # Display results
        if args.format == 'terminal':
            display_terminal_results(top_papers, args, len(papers))
        elif args.format == 'markdown':
            display_markdown_results(top_papers, args, len(papers))
        elif args.format == 'json':
            display_json_results(top_papers, args, len(papers))
        
        # Save to file if requested
        if args.output:
            save_results_to_file(ranked_papers, args)
            print(f"\n💾 Results saved to {args.output}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

def print_header(args):
    """Print a nice header for the CLI."""
    print("=" * 80)
    print("🤖 ArXiv AI Paper Tracker with Altmetric Ranking")
    print("=" * 80)
    print(f"📅 Search period: Last {args.days} days")
    print(f"📊 Display count: Top {args.count} papers")
    print(f"🔍 Max results: {args.max_results} papers")
    if args.categories:
        print(f"🏷️  Categories: {', '.join(args.categories)}")
    else:
        print("🏷️  Categories: All AI categories (cs.AI, cs.LG, cs.CL, cs.CV, cs.NE, stat.ML)")
    print(f"📈 Altmetric: {'Disabled' if args.no_altmetric else 'Enabled'}")
    print()

def display_terminal_results(papers: List[ArxivPaper], args, total_count: int):
    """Display results in terminal format with colors."""
    print("\n" + "=" * 80)
    print(f"🏆 TOP {len(papers)} AI PAPERS BY POPULARITY")
    print("=" * 80)
    
    for i, paper in enumerate(papers, 1):
        print(f"\n#{i}. {paper.title}")
        print("─" * min(len(paper.title) + 4, 80))
        
        # Authors
        if len(paper.authors) <= 3:
            authors_str = ", ".join(paper.authors)
        else:
            authors_str = ", ".join(paper.authors[:3]) + f" et al. ({len(paper.authors)} total)"
        print(f"👥 Authors: {authors_str}")
        
        # Date and categories
        main_categories = [cat for cat in paper.categories if cat in ['cs.AI', 'cs.LG', 'cs.CL', 'cs.CV', 'cs.NE', 'stat.ML']]
        categories_str = ", ".join(main_categories[:3])
        print(f"📅 Published: {paper.published.strftime('%Y-%m-%d')} | 🏷️ Categories: {categories_str}")
        
        # Altmetric info
        if paper.altmetric_score and paper.altmetric_score > 0:
            altmetric_info = f"📊 Altmetric Score: {paper.altmetric_score:.1f}"
            
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
            
            print(altmetric_info)
        else:
            print("📊 Altmetric Score: No data")
        
        # Abstract (truncated)
        abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
        print(f"\n📄 Abstract: {abstract}")
        
        # Links
        print(f"🔗 Links: arXiv: {paper.arxiv_url}")
        print(f"         PDF: {paper.pdf_url}")
        
        if i < len(papers):
            print("\n" + "─" * 80)
    
    # Summary
    print(f"\n📈 Summary: Displayed top {len(papers)} papers out of {total_count} found")
    if not args.no_altmetric:
        avg_score = sum(p.altmetric_score or 0 for p in papers) / len(papers) if papers else 0
        print(f"📊 Average Altmetric score: {avg_score:.1f}")

def display_markdown_results(papers: List[ArxivPaper], args, total_count: int):
    """Display results in markdown format."""
    print(f"\n# Top {len(papers)} AI Papers by Popularity\n")
    print(f"**Search Period:** Last {args.days} days  ")
    print(f"**Total Papers Found:** {total_count}  ")
    print(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    for i, paper in enumerate(papers, 1):
        print(f"## {i}. {paper.title}\n")
        
        # Authors
        if len(paper.authors) <= 3:
            authors_str = ", ".join(paper.authors)
        else:
            authors_str = ", ".join(paper.authors[:3]) + f" et al. ({len(paper.authors)} total)"
        print(f"**Authors:** {authors_str}  ")
        
        # Date and categories
        main_categories = [cat for cat in paper.categories if cat in ['cs.AI', 'cs.LG', 'cs.CL', 'cs.CV', 'cs.NE', 'stat.ML']]
        categories_str = ", ".join(main_categories[:3])
        print(f"**Published:** {paper.published.strftime('%Y-%m-%d')} | **Categories:** {categories_str}  ")
        
        # Altmetric
        if paper.altmetric_score and paper.altmetric_score > 0:
            print(f"**Altmetric Score:** {paper.altmetric_score:.1f}  ")
        
        # Abstract
        print(f"\n{paper.abstract}\n")
        
        # Links
        print(f"**Links:** [arXiv]({paper.arxiv_url}) | [PDF]({paper.pdf_url})\n")
        print("---\n")

def display_json_results(papers: List[ArxivPaper], args, total_count: int):
    """Display results in JSON format."""
    results = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'search_days': args.days,
            'total_papers_found': total_count,
            'papers_displayed': len(papers),
            'altmetric_enabled': not args.no_altmetric
        },
        'papers': []
    }
    
    for paper in papers:
        paper_dict = {
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
            'altmetric_data': paper.altmetric_data
        }
        results['papers'].append(paper_dict)
    
    print(json.dumps(results, indent=2, default=str))

def save_results_to_file(papers: List[ArxivPaper], args):
    """Save results to a JSON file."""
    results = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'search_days': args.days,
            'total_papers': len(papers),
            'altmetric_enabled': not args.no_altmetric,
            'categories_searched': args.categories or ['cs.AI', 'cs.LG', 'cs.CL', 'cs.CV', 'cs.NE', 'stat.ML']
        },
        'papers': []
    }
    
    for paper in papers:
        paper_dict = {
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
            'altmetric_data': paper.altmetric_data
        }
        results['papers'].append(paper_dict)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 