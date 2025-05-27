#!/usr/bin/env python3
"""
Test script to demonstrate the new priority scoring system with higher Altmetric weighting.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from arxiv_tracker import ArxivAltmetricTracker

async def test_priority_scoring():
    """Test the new priority scoring system."""
    print("🧪 Testing New Priority Scoring System")
    print("=" * 60)
    print("New formula: (altmetric_score + 1)² + bonuses")
    print("This heavily weights papers with any Altmetric data")
    print()
    
    try:
        async with ArxivAltmetricTracker() as tracker:
            # Get recent papers with Altmetric data
            papers = await tracker.get_trending_papers(
                days_back=7,  # Look back further to get more variety
                count=15,
                include_altmetric=True
            )
            
            if not papers:
                print("❌ No papers found for testing")
                return
            
            print(f"📊 Found {len(papers)} papers for analysis")
            print()
            
            # Show examples of different scoring scenarios
            print("🏆 Priority Score Examples:")
            print("-" * 60)
            
            # Group papers by Altmetric score ranges
            high_altmetric = [p for p in papers if p.altmetric_score and p.altmetric_score >= 5]
            medium_altmetric = [p for p in papers if p.altmetric_score and 1 <= p.altmetric_score < 5]
            low_altmetric = [p for p in papers if p.altmetric_score and 0 < p.altmetric_score < 1]
            no_altmetric = [p for p in papers if not p.altmetric_score or p.altmetric_score == 0]
            
            def show_paper_examples(papers, category_name, max_examples=3):
                if papers:
                    print(f"\n{category_name}:")
                    for i, paper in enumerate(papers[:max_examples]):
                        altmetric_str = f"{paper.altmetric_score:.1f}" if paper.altmetric_score else "0"
                        hours_old = (datetime.now(timezone.utc) - paper.published).total_seconds() / 3600
                        
                        print(f"  {i+1}. Priority: {paper.priority_score:.1f} | Altmetric: {altmetric_str} | Age: {hours_old:.1f}h")
                        print(f"     {paper.title[:70]}...")
                        
                        # Show score breakdown
                        if paper.altmetric_score and paper.altmetric_score > 0:
                            base_score = (paper.altmetric_score + 1) ** 2
                            print(f"     Base Altmetric: ({altmetric_str} + 1)² = {base_score:.1f}")
                        
                        print()
            
            # Show examples from each category
            show_paper_examples(high_altmetric, "🔥 High Altmetric (≥5.0)")
            show_paper_examples(medium_altmetric, "📈 Medium Altmetric (1.0-4.9)")
            show_paper_examples(low_altmetric, "📊 Low Altmetric (0.1-0.9)")
            show_paper_examples(no_altmetric, "📝 No Altmetric Data")
            
            # Show overall statistics
            print("📈 Scoring Statistics:")
            print("-" * 40)
            
            if papers:
                scores = [p.priority_score for p in papers]
                altmetric_scores = [p.altmetric_score for p in papers if p.altmetric_score and p.altmetric_score > 0]
                
                print(f"Priority Score Range: {min(scores):.1f} - {max(scores):.1f}")
                print(f"Average Priority Score: {sum(scores)/len(scores):.1f}")
                
                if altmetric_scores:
                    print(f"Papers with Altmetric: {len(altmetric_scores)}/{len(papers)} ({len(altmetric_scores)/len(papers)*100:.1f}%)")
                    print(f"Average Altmetric Score: {sum(altmetric_scores)/len(altmetric_scores):.1f}")
                    
                    # Show how the new formula affects ranking
                    papers_with_altmetric = [p for p in papers if p.altmetric_score and p.altmetric_score > 0]
                    if papers_with_altmetric:
                        top_altmetric = max(papers_with_altmetric, key=lambda p: p.altmetric_score or 0)
                        print(f"\nTop Altmetric Paper:")
                        altmetric_score = top_altmetric.altmetric_score or 0
                        print(f"  Altmetric: {altmetric_score:.1f}")
                        print(f"  Priority: {top_altmetric.priority_score:.1f}")
                        print(f"  Formula: ({altmetric_score:.1f} + 1)² = {(altmetric_score + 1)**2:.1f} + bonuses")
                        print(f"  Title: {top_altmetric.title[:60]}...")
                
                print()
                print("✅ New scoring system heavily favors papers with Altmetric data!")
                print("   Even a score of 1.0 gets (1+1)² = 4 base points")
                print("   A score of 5.0 gets (5+1)² = 36 base points")
                print("   A score of 10.0 gets (10+1)² = 121 base points + 100 bonus = 221+ total")
            
    except Exception as e:
        print(f"❌ Error testing priority scoring: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_priority_scoring()) 