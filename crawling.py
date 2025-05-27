from baml_py import Image
from baml_client.sync_client import b
from crawl4ai import CrawlerRunConfig

_crawler = None

def set_crawler(crawler_instance):
    global _crawler
    _crawler = crawler_instance

async def fetch_and_prepare_post_data(url):
    if _crawler is None:
        raise RuntimeError("Crawler has not been set. Call set_crawler() at startup.")
    await _crawler.start()
    result = await _crawler.arun(url=url, config=CrawlerRunConfig(
        exclude_external_images=False,
        wait_for_images=True
    ))
    if result and hasattr(result, 'markdown'):
        article = b.ParseArticle(result.markdown)
        summary = b.WriteArticleSummary(article)
        with open("urls.txt", "a", encoding="utf-8") as url_file:
            url_file.write(f"{url}\t{summary}\n")
        post = b.WritePost(summary=summary.summary, url=url)
        post_data = {
            "content": post.text if hasattr(post, 'text') else str(post),
            "url": post.url if hasattr(post, 'url') else url
        }
        return article, post_data
    else:
        with open("urls.txt", "a", encoding="utf-8") as url_file:
            url_file.write(f"{url}\t[Could not fetch article content]\n")
        return None, None

def fix_arxiv_image_url(paper_url: str, image_url: str) -> str:
    """Ensure arxiv image URLs include the paper ID and are valid image URLs."""
    if not image_url or not paper_url:
        return image_url
    if '/html/' not in paper_url:
        return image_url
        
    # Get the paper ID from the URL
    paper_id = paper_url.split('/html/')[-1].strip('/')
    
    # Remove any section references (#S1.F1, etc)
    if '#' in image_url:
        image_url = image_url.split('#')[0]
        
    # If it's a figure reference, convert to actual image URL
    if image_url.endswith('.F1') or image_url.endswith('.F2'):
        figure_num = image_url.split('.')[-1][1:]  # Extract number from F1, F2, etc
        return f"https://arxiv.org/html/{paper_id}/x{figure_num}.png"
        
    # For direct image references, ensure full path
    if image_url.startswith('https://arxiv.org/html/'):
        return f"https://arxiv.org/html/{paper_id}/{image_url.split('/')[-1]}"
        
    return image_url

async def prepare_thread_data(url):
    """Fetch, parse, and summarize the paper, and prepare thread data for posting."""
    if _crawler is None:
        raise RuntimeError("Crawler has not been set. Call set_crawler() at startup.")
    await _crawler.start()
    result = await _crawler.arun(url=url, config=CrawlerRunConfig(
        exclude_external_images=False,
        wait_for_images=True
    ))
    
    if result and hasattr(result, 'markdown'):
        # Use the Paper flow for research papers
        paper = b.ParsePaper(result.markdown)
        
        # Fix any partial arxiv image URLs
        if hasattr(paper, 'figures'):
            for fig in paper.figures:
                if hasattr(fig, 'url') and fig.url:
                    fig.url = fix_arxiv_image_url(url, fig.url)
        
        paper_summary = b.WritePaperSummary(paper)
        figure_summaries = [b.WriteFigureSummary(Image.from_url(fig.url)) for fig in paper.figures]
        summary_text = "\n\n".join([p.text for p in paper_summary.summary])
        
        thread = b.WriteThread(url=url, summary=summary_text, figures=figure_summaries)
        for i, post in enumerate(thread.posts):
            print(f"Post {i}:")
            print(f"Text: {post.text}")
            print(f"Image URL: {getattr(post, 'image_url', None)}")
            if hasattr(post, 'image_url') and post.image_url:
                post.image_url = fix_arxiv_image_url(url, post.image_url)
        
        # thread.posts is a list of Post objects
        thread_data = {
            "posts": []
        }
        # First post includes URL
        if thread.posts:
            thread_data["posts"].append({
                "content": thread.posts[0].text,
                "url": url
            })
            # Remaining posts don't include URL but may include images
            thread_data["posts"].extend([
                {"content": post.text, "image_url": post.image_url} for post in thread.posts[1:]
            ])
        return thread_data, paper, thread_data["posts"][0] if thread_data["posts"] else None
    else:
        return None, None, None