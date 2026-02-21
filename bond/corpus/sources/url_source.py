"""Blog URL scraper using trafilatura for article extraction."""

import json
import trafilatura
from trafilatura.sitemaps import sitemap_search
from bond.config import settings
from bond.corpus.ingestor import CorpusIngestor


def scrape_blog(url: str) -> list[dict]:
    """
    Discover all post URLs via sitemap/feed, extract each article.
    Returns list of {"url": str, "title": str, "text": str}.
    Failures: skip and warn (per CONTEXT.md policy).
    """
    articles = []

    # Discover post URLs via sitemap; fallback to single URL
    urls = sitemap_search(url) or [url]
    max_posts = settings.max_blog_posts

    if len(urls) > max_posts:
        print(
            f"WARN: Found {len(urls)} posts at {url}; limiting to {max_posts} (MAX_BLOG_POSTS)"
        )
        urls = list(urls)[:max_posts]

    print(f"INFO: Scraping {len(urls)} posts from {url}")

    for post_url in urls:
        try:
            downloaded = trafilatura.fetch_url(post_url)
            if downloaded is None:
                print(f"WARN: Could not fetch {post_url} — skipping")
                continue
            raw = trafilatura.extract(downloaded, output_format="json")
            if raw is None:
                print(f"WARN: No article content found at {post_url} — skipping")
                continue
            data = json.loads(raw)
            text = data.get("text", "")
            if not text.strip():
                print(f"WARN: Empty text extracted from {post_url} — skipping")
                continue
            articles.append(
                {
                    "url": post_url,
                    "title": data.get("title") or post_url,
                    "text": text,
                }
            )
        except Exception as e:
            print(f"WARN: {post_url} failed ({type(e).__name__}: {e}) — skipping")

    return articles


def ingest_blog(url: str, source_type: str) -> dict:
    """
    Scrape blog and ingest all articles. Returns summary dict.
    """
    articles = scrape_blog(url)
    if not articles:
        print(f"WARN: No articles extracted from {url}")
        return {
            "articles_ingested": 0,
            "total_chunks": 0,
            "warnings": [f"No articles found at {url}"],
        }

    ingestor = CorpusIngestor()
    total_chunks = 0
    ingested_count = 0
    warnings = []

    for article in articles:
        result = ingestor.ingest(
            text=article["text"],
            title=article["title"],
            source_type=source_type,
            source_url=article["url"],
        )
        if result["chunks_added"] > 0:
            total_chunks += result["chunks_added"]
            ingested_count += 1
        else:
            warnings.append(f"Article too short to chunk: {article['url']}")

    return {
        "articles_ingested": ingested_count,
        "total_chunks": total_chunks,
        "warnings": warnings,
    }
