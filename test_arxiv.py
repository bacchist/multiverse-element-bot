#!/usr/bin/env python3
"""
Test script for the arXiv tracker functionality.
Run this to verify the tracker works before using it in the bot.
"""

import subprocess
import sys
import os

def test_arxiv_tracker():
    """Test the arXiv tracker with different configurations."""
    print("🧪 Testing arXiv AI Paper Tracker...")
    print("=" * 60)
    
    # Check if the main script exists
    if not os.path.exists('arxiv_tracker.py'):
        print("❌ arxiv_tracker.py not found!")
        return False
    
    tests = [
        {
            'name': 'Basic functionality test',
            'args': ['--days', '2', '--count', '3', '--no-altmetric'],
            'description': 'Quick test without Altmetric (faster)'
        },
        {
            'name': 'Help command test',
            'args': ['--help'],
            'description': 'Display help information'
        },
        {
            'name': 'JSON output test',
            'args': ['--days', '1', '--count', '2', '--format', 'json', '--no-altmetric'],
            'description': 'Test JSON output format'
        }
    ]
    
    for i, test in enumerate(tests, 1):
        print(f"\n🔬 Test {i}: {test['name']}")
        print(f"   {test['description']}")
        print(f"   Command: python arxiv_tracker.py {' '.join(test['args'])}")
        print("   " + "-" * 50)
        
        try:
            # Run the command
            result = subprocess.run(
                [sys.executable, 'arxiv_tracker.py'] + test['args'],
                capture_output=True,
                text=True,
                timeout=60  # 1 minute timeout
            )
            
            if result.returncode == 0:
                print("   ✅ Test passed!")
                if test['args'] == ['--help']:
                    # For help command, show first few lines
                    lines = result.stdout.split('\n')[:10]
                    print("   📄 Output preview:")
                    for line in lines:
                        if line.strip():
                            print(f"      {line}")
                else:
                    # For other commands, show summary
                    lines = result.stdout.split('\n')
                    summary_lines = [line for line in lines if any(marker in line for marker in ['Found', 'Summary', 'TOP', '📈', '✅'])]
                    if summary_lines:
                        print("   📊 Summary:")
                        for line in summary_lines[:3]:
                            print(f"      {line}")
            else:
                print(f"   ❌ Test failed with exit code {result.returncode}")
                if result.stderr:
                    print(f"   Error: {result.stderr[:200]}...")
                    
        except subprocess.TimeoutExpired:
            print("   ⏰ Test timed out (this might happen with Altmetric requests)")
        except Exception as e:
            print(f"   ❌ Test error: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 Manual Testing Suggestions:")
    print("=" * 60)
    print("Try these commands manually to test different features:")
    print()
    print("1. Basic usage (fast):")
    print("   python arxiv_tracker.py --days 3 --count 5 --no-altmetric")
    print()
    print("2. With Altmetric data (slower):")
    print("   python arxiv_tracker.py --days 2 --count 3")
    print()
    print("3. Specific categories:")
    print("   python arxiv_tracker.py --categories cs.AI cs.LG --days 7")
    print()
    print("4. Save to file:")
    print("   python arxiv_tracker.py --days 1 --output today_papers.json")
    print()
    print("5. Markdown output:")
    print("   python arxiv_tracker.py --format markdown --days 2 --count 3")
    print()
    print("6. Verbose mode:")
    print("   python arxiv_tracker.py --verbose --days 1 --count 2")
    print()
    print("💡 The script is now ready to use as a standalone CLI tool!")
    print("   Use 'python arxiv_tracker.py --help' for full documentation.")
    
    return True

if __name__ == "__main__":
    success = test_arxiv_tracker()
    sys.exit(0 if success else 1) 