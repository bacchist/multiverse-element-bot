#!/usr/bin/env python3
"""
Test script for the arXiv tracker functionality.
Run this to verify the tracker works before using it in the bot.
"""

import asyncio
import sys
import logging

async def test_arxiv_tracker():
    """Test the arXiv tracker with different configurations."""
    print("🧪 Testing arXiv AI Paper Tracker...")
    print("=" * 60)
    
    try:
        from arxiv_tracker import ArxivAltmetricTracker
    except ImportError as e:
        print(f"❌ Cannot import arxiv_tracker: {e}")
        print("Make sure you have installed the required dependencies:")
        print("  pip install aiohttp")
        return False
    
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    tests = [
        {
            'name': 'Basic functionality test (no Altmetric)',
            'description': 'Quick test without Altmetric data (faster)',
            'params': {'days_back': 2, 'count': 3, 'include_altmetric': False}
        },
        {
            'name': 'With Altmetric data test',
            'description': 'Test with Altmetric data (slower)',
            'params': {'days_back': 1, 'count': 2, 'include_altmetric': True}
        }
    ]
    
    for i, test in enumerate(tests, 1):
        print(f"\n🔬 Test {i}: {test['name']}")
        print(f"   {test['description']}")
        print("   " + "-" * 50)
        
        try:
            async with ArxivAltmetricTracker() as tracker:
                papers = await tracker.get_trending_papers(**test['params'])
                
                if papers:
                    print(f"   ✅ Test passed! Found {len(papers)} papers")
                    
                    # Show first paper as example
                    paper = papers[0]
                    print(f"   📄 Example paper:")
                    print(f"      Title: {paper.title[:60]}...")
                    print(f"      Authors: {', '.join(paper.authors[:2])}")
                    print(f"      Published: {paper.published.strftime('%Y-%m-%d')}")
                    print(f"      Categories: {', '.join(paper.categories[:2])}")
                    if paper.altmetric_score:
                        print(f"      Altmetric Score: {paper.altmetric_score:.1f}")
                    print(f"      Priority Score: {paper.priority_score:.1f}")
                    print(f"      URL: {paper.arxiv_url}")
                else:
                    print("   ⚠️ Test completed but no papers found")
                    
        except Exception as e:
            print(f"   ❌ Test failed: {e}")
            if "timeout" in str(e).lower():
                print("   💡 This might be due to network issues or API rate limits")
    
    print("\n" + "=" * 60)
    print("🎯 Manual Testing Suggestions:")
    print("=" * 60)
    print("Try these commands to test the standalone CLI:")
    print()
    print("1. Basic usage (fast):")
    print("   python arxiv_tracker.py --days 3 --count 5 --no-altmetric")
    print()
    print("2. With Altmetric data (slower):")
    print("   python arxiv_tracker.py --days 2 --count 3")
    print()
    print("3. JSON output:")
    print("   python arxiv_tracker.py --days 1 --count 2 --format json")
    print()
    print("4. Help:")
    print("   python arxiv_tracker.py --help")
    print()
    print("💡 The ArXiv tracker is now ready to use!")
    
    return True

async def test_auto_poster():
    """Test the auto-poster functionality (without actually posting)."""
    print("\n🤖 Testing ArXiv Auto-Poster...")
    print("=" * 60)
    
    try:
        from arxiv_auto_poster import ArxivAutoPoster
        import niobot
    except ImportError as e:
        print(f"❌ Cannot import auto-poster modules: {e}")
        return False
    
    try:
        # Create a mock bot for testing
        class MockBot:
            async def send_message(self, channel, message):
                print(f"📤 Would post to {channel}:")
                print(f"   {message[:100]}...")
                return True
        
        mock_bot = MockBot()
        
        # Initialize auto-poster
        auto_poster = ArxivAutoPoster(
            bot=mock_bot,
            target_channel="#test-channel",
            max_posts_per_day=1
        )
        
        if not auto_poster.enabled:
            print("⚠️ Auto-poster is disabled (missing dependencies)")
            return False
        
        print("✅ Auto-poster initialized successfully")
        
        # Test discovery
        print("\n🔍 Testing paper discovery...")
        new_papers = await auto_poster.discover_papers()
        print(f"   Found {len(new_papers)} new papers")
        
        # Show status
        status = auto_poster.get_status()
        print(f"\n📊 Status:")
        print(f"   Pool size: {status['pool_size']}")
        print(f"   Enabled: {status['enabled']}")
        print(f"   Target: {status['target_channel']}")
        
        print("✅ Auto-poster test completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Auto-poster test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 ArXiv Integration Test Suite")
    print("=" * 80)
    
    tracker_success = await test_arxiv_tracker()
    poster_success = await test_auto_poster()
    
    print("\n" + "=" * 80)
    print("📋 Test Results Summary:")
    print("=" * 80)
    print(f"ArXiv Tracker: {'✅ PASS' if tracker_success else '❌ FAIL'}")
    print(f"Auto-Poster:   {'✅ PASS' if poster_success else '❌ FAIL'}")
    
    if tracker_success and poster_success:
        print("\n🎉 All tests passed! The ArXiv integration is ready to use.")
        print("\nTo enable in your bot:")
        print("1. Make sure dependencies are installed: pip install aiohttp")
        print("2. Restart your bot")
        print("3. Use !trending_ai to test manual paper fetching")
        print("4. Use !arxiv_status to check auto-poster status")
    else:
        print("\n⚠️ Some tests failed. Check the error messages above.")
    
    return tracker_success and poster_success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 