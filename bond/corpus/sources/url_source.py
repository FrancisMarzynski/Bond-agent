"""Blog URL scraper using trafilatura for article extraction."""

import json
import logging

import trafilatura
from trafilatura.sitemaps import sitemap_search

from bond.config import settings
from bond.corpus.ingestor import CorpusIngestor
from bond.security import UnsafeUrlError, validate_public_url

log = logging.getLogger(__name__)


def scrape_blog(url: str) -> list[dict]:
    """
    Discover all post URLs via sitemap/feed, extract each article.
    Returns list of {"url": str, "title": str, "text": str}.
    Failures: skip and warn (per CONTEXT.md policy).
    """
    articles = []

    validated_url = validate_public_url(
        url,
        allow_private=settings.allow_private_url_ingest,
    )

    # Discover post URLs via sitemap; fallback to single URL
    urls = sitemap_search(validated_url) or [validated_url]
    max_posts = settings.max_blog_posts

    if len(urls) > max_posts:
        log.warning(
            "Found %d posts at %s; limiting to %d (MAX_BLOG_POSTS)",
            len(urls),
            validated_url,
            max_posts,
        )
        urls = list(urls)[:max_posts]

    log.info("Scraping %d posts from %s", len(urls), validated_url)

    for post_url in urls:
        try:
            safe_post_url = validate_public_url(
                post_url,
                allow_private=settings.allow_private_url_ingest,
            )
        except UnsafeUrlError as e:
            log.warning("%s rejected as unsafe URL (%s) — skipping", post_url, e)
            continue

        try:
            downloaded = trafilatura.fetch_url(safe_post_url)
            if downloaded is None:
                log.warning("Could not fetch %s — skipping", safe_post_url)
                continue
            raw = trafilatura.extract(downloaded, output_format="json")
            if raw is None:
                log.warning("No article content found at %s — skipping", safe_post_url)
                continue
            data = json.loads(raw)
            text = data.get("text", "")
            if not text.strip():
                log.warning("Empty text extracted from %s — skipping", safe_post_url)
                continue
            articles.append(
                {
                    "url": safe_post_url,
                    "title": data.get("title") or safe_post_url,
                    "text": text,
                }
            )
        except Exception as e:
            log.warning("%s failed (%s: %s) — skipping", safe_post_url, type(e).__name__, e)

    return articles


def ingest_blog(url: str, source_type: str) -> dict:
    """
    Scrape blog and ingest all articles. Returns summary dict.
    """
    articles = scrape_blog(url)
    if not articles:
        log.warning("No articles extracted from %s", url)
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
