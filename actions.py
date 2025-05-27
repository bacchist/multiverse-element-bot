from typing import Optional, Tuple
from crawling import prepare_thread_data, fetch_and_prepare_post_data
from config import post_client  # This is now an instance of Poster

RESEARCH_DOMAINS = [
    "arxiv.org", "doi.org", "springer.com", "nature.com", "sciencedirect.com", "ieeexplore.ieee.org"
]

def is_research_paper_url(url: str) -> bool:
    """Return True if the URL is likely a research paper."""
    return any(domain in url for domain in RESEARCH_DOMAINS)

async def process_url(url: str) -> None:
    """Fetch, summarize, and post the URL as a single post or thread using Poster."""
    print(f"process_url: Executing for URL {url}")
    try:
        if is_research_paper_url(url):
            print("process_url: Detected research paper, preparing thread.")
            # You could expand this to prepare multiple posts for the thread if desired
            thread_data, paper, first_post = await prepare_thread_data(url)
            if not thread_data or not thread_data["posts"]:
                print("process_url: No thread_data returned, aborting.")
                return
            await post_client.post_thread(thread_data)
        else:
            print("process_url: Not a research paper, preparing single post.")
            article, post_data = await fetch_and_prepare_post_data(url)
            if not post_data:
                print("process_url: No post_data returned, aborting.")
                return
            await post_client.post_single(post_data)
    except Exception as e:
        print(f"process_url: Exception during fetch/summarize: {e}")
        return 