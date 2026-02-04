"""
Article Extraction from Newsletter HTML
=========================================

Two article types, classified at extraction time:

  link   – the newsletter is linking out to someone else's article.
           The text the newsletter author wrote around that link (the "blurb")
           IS the summary.  No Claude call needed downstream.

  essay  – the newsletter IS the article.  Long-form original writing that
           lives entirely inside the email.  Needs Claude to summarise it.

Classification rules (checked in order):
  1. Force-tag: if newsletter_name matches anything in config.ESSAY_NEWSLETTERS,
     every article from that source is an essay.
  2. Heuristic: no outbound URL  ->  essay.
  3. Heuristic: URL points back to the newsletter's own domain  ->  essay.
  4. Everything else  ->  link.

Extraction strategies (tried in priority order):
  1. Section-based  – split on h2/h3 boundaries.
  2. Link-based     – each article-looking <a> becomes its own entry.
  3. Fallback       – whole email body = one article.
"""
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAYWALL_PHRASES = [
    'subscribe to read', 'paywall', 'premium content',
    'unlock this article', 'sign up to continue', 'member only',
    'paid subscribers only', 'read the full article', 'continue reading',
    'behind a paywall', 'premium member', 'subscription required'
]

NOISE_PATH_SEGMENTS = {
    'disclaimer', 'legal', 'terms', 'privacy', 'cookie',
    'unsubscribe', 'preferences', 'settings', 'about',
    'contact', 'careers', 'investors', 'ir', 'press',
    'login', 'signup', 'register', 'help', 'support',
    'faq', 'sitemap', 'robots', 'policy', 'policies',
}

NOISE_ANCHOR_PHRASES = [
    'disclaimer', 'terms of', 'privacy policy', 'cookie',
    'unsubscribe', 'view in browser', 'read in browser',
    'click here to unsubscribe', 'manage preferences',
    'forward this email', 'view online', 'web version',
]

# Max characters of blurb text to keep (newsletter blurbs are short by nature)
MAX_BLURB_CHARS = 600


class ArticleExtractor:
    """Extract structured articles from raw newsletter HTML."""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def extract_from_email(self, html_content: str, newsletter_name: str = '',
                           newsletter_email: str = '',
                           received_timestamp: str = '') -> List[Dict[str, Any]]:
        """
        Main extraction method.

        Returns:
            List of article dicts.  Each has:
                title, url, content, blurb, word_count,
                article_type ('link' | 'essay'),
                paywall_detected, author, publish_date,
                newsletter_name, newsletter_email, received_timestamp.
        """
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, 'html.parser')

        # Try strategies in order
        articles = self._extract_by_sections(soup)
        if not articles:
            articles = self._extract_by_links(soup)
        if not articles:
            articles = self._extract_fallback(soup)

        # Stamp shared metadata, classify, and filter
        force_essay = self._is_essay_newsletter(newsletter_name)
        result = []
        for a in articles:
            a['newsletter_name']      = newsletter_name
            a['newsletter_email']     = newsletter_email
            a['received_timestamp']   = received_timestamp
            a['paywall_detected']     = self._detect_paywall(a.get('content', ''))
            a['article_type']         = self._classify(a, newsletter_email, force_essay)

            if a.get('word_count', 0) >= config.MIN_WORD_COUNT:
                result.append(a)

        return result

    # ------------------------------------------------------------------
    # Strategy 1 – section-based (h2 / h3 boundaries)
    # ------------------------------------------------------------------
    def _extract_by_sections(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Walk top-level children of <body>.  Each h2/h3 starts a new bucket.
        Text before the first heading is discarded (header chrome).
        """
        body = soup.find('body') or soup
        articles: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for element in body.children:
            if not hasattr(element, 'name'):
                if current is not None:
                    current['_raw_text'] += element.strip() + ' '
                continue

            if element.name in ('h2', 'h3'):
                if current is not None:
                    articles.append(self._finalise(current))

                title = element.get_text(strip=True)
                link  = self._best_link_in(element)
                current = {
                    'title':    title,
                    'url':      link or '',
                    '_raw_text': '',
                    'author':   None,
                    'publish_date': None,
                }
            else:
                if current is not None:
                    current['_raw_text'] += element.get_text(separator=' ', strip=True) + ' '
                    if not current['url']:
                        current['url'] = self._best_link_in(element) or ''

        if current is not None:
            articles.append(self._finalise(current))

        return [a for a in articles if a['word_count'] > 0]

    # ------------------------------------------------------------------
    # Strategy 2 – link-based
    # ------------------------------------------------------------------
    def _extract_by_links(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Each <a> that looks like an article link becomes its own entry.
        The closest block-level parent's text becomes both content and blurb.
        """
        articles: List[Dict[str, Any]] = []
        seen_urls: set = set()

        for a_tag in soup.find_all('a', href=True):
            url = a_tag['href'].strip()

            if not url.startswith('http'):
                continue
            if self._is_noise_url(url, a_tag.get_text(strip=True)):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = a_tag.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            # Walk up to find a block-level parent with real text
            content_block = a_tag
            for _ in range(5):
                parent = content_block.parent
                if parent is None:
                    break
                if parent.name in ('td', 'div', 'section', 'article', 'li', 'p'):
                    content_block = parent
                    break
                content_block = parent

            content = content_block.get_text(separator=' ', strip=True)

            articles.append({
                'title':          title,
                'url':            url,
                'content':        content,
                'blurb':          self._extract_blurb(content, title),
                'content_snippet': content[:500],
                'word_count':     len(content.split()),
                'author':         None,
                'publish_date':   None,
            })

        return articles

    # ------------------------------------------------------------------
    # Strategy 3 – fallback (whole email = one article)
    # ------------------------------------------------------------------
    def _extract_fallback(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Last resort: treat the entire email body as a single article."""
        text = soup.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text).strip()

        title = 'Newsletter'
        for line in text.split('\n'):
            line = line.strip()
            if 10 < len(line) < 120:
                title = line
                break

        return [{
            'title':          title,
            'url':            '',
            'content':        text,
            'blurb':          '',          # essay — blurb is meaningless here
            'content_snippet': text[:500],
            'word_count':     len(text.split()),
            'author':         None,
            'publish_date':   None,
        }]

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    @staticmethod
    def _is_essay_newsletter(newsletter_name: str) -> bool:
        """True if this newsletter is in the known-essay list."""
        name_lower = (newsletter_name or '').lower()
        return any(kw in name_lower for kw in config.ESSAY_NEWSLETTERS)

    @staticmethod
    def _classify(article: Dict[str, Any], newsletter_email: str,
                  force_essay: bool) -> str:
        """
        Return 'essay' or 'link'.

        Rules (checked in order):
          1. force_essay flag (newsletter is in ESSAY_NEWSLETTERS)  ->  essay
          2. no outbound URL  ->  essay
          3. URL points back to newsletter's own domain  ->  essay
          4. everything else  ->  link
        """
        if force_essay:
            return 'essay'

        url = (article.get('url') or '').strip()

        # No URL at all
        if not url:
            return 'essay'

        # URL points back to the newsletter's own domain
        if '@' in (newsletter_email or ''):
            nl_domain = newsletter_email.split('@')[1].lower()
            if nl_domain in url.lower():
                return 'essay'

        return 'link'

    # ------------------------------------------------------------------
    # Blurb extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_blurb(content: str, title: str) -> str:
        """
        Pull the newsletter-author's blurb out of the content block.

        The blurb is everything in the content block that isn't the title
        itself.  We strip the title text from the front if it appears there
        (common: title is repeated as the first line of the block).
        Then trim to MAX_BLURB_CHARS and clean up whitespace.
        """
        blurb = content.strip()

        # If the content starts with the title, strip it
        if blurb.lower().startswith(title.lower()):
            blurb = blurb[len(title):].strip()

        # Collapse whitespace
        blurb = re.sub(r'\s+', ' ', blurb).strip()

        # Trim
        if len(blurb) > MAX_BLURB_CHARS:
            blurb = blurb[:MAX_BLURB_CHARS].rsplit(' ', 1)[0] + ' \u2026'

        return blurb

    # ------------------------------------------------------------------
    # Finalise a section bucket  ->  article dict
    # ------------------------------------------------------------------
    @staticmethod
    def _finalise(bucket: Dict[str, Any]) -> Dict[str, Any]:
        """Turn a raw-text bucket into a finished article dict."""
        content = re.sub(r'\s+', ' ', bucket['_raw_text']).strip()
        title   = bucket['title']

        # Blurb: strip title from front of content if present, then trim
        blurb = content
        if blurb.lower().startswith(title.lower()):
            blurb = blurb[len(title):].strip()
        blurb = re.sub(r'\s+', ' ', blurb).strip()
        if len(blurb) > MAX_BLURB_CHARS:
            blurb = blurb[:MAX_BLURB_CHARS].rsplit(' ', 1)[0] + ' \u2026'

        return {
            'title':          title,
            'url':            bucket['url'],
            'content':        content,
            'blurb':          blurb,
            'content_snippet': content[:500],
            'word_count':     len(content.split()),
            'author':         bucket.get('author'),
            'publish_date':   bucket.get('publish_date'),
        }

    # ------------------------------------------------------------------
    # URL / noise helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _is_noise_url(url: str, anchor_text: str = '') -> bool:
        lower_url  = url.lower()
        lower_text = anchor_text.lower()

        for domain in ('twitter.com', 'facebook.com', 'instagram.com',
                       'linkedin.com', 'youtube.com', 'mailto:', 'javascript:'):
            if domain in lower_url:
                return True

        try:
            path_parts = urlparse(lower_url).path.strip('/').split('/')
        except Exception:
            path_parts = []
        if any(seg in NOISE_PATH_SEGMENTS for seg in path_parts):
            return True

        if any(phrase in lower_text for phrase in NOISE_ANCHOR_PHRASES):
            return True

        return False

    @staticmethod
    def _score_link(url: str, anchor_text: str) -> int:
        lower_url  = url.lower()
        lower_text = anchor_text.lower()

        for domain in ('twitter.com', 'facebook.com', 'instagram.com',
                       'linkedin.com', 'youtube.com', 'mailto:', 'javascript:'):
            if domain in lower_url:
                return 0
        try:
            path_parts = urlparse(lower_url).path.strip('/').split('/')
        except Exception:
            path_parts = []
        if any(seg in NOISE_PATH_SEGMENTS for seg in path_parts):
            return 0
        if any(phrase in lower_text for phrase in NOISE_ANCHOR_PHRASES):
            return 0

        score = 1

        words = len(anchor_text.split())
        if words >= 4:
            score += 3
        elif words >= 2:
            score += 1

        depth = len([p for p in path_parts if p])
        if depth >= 3:
            score += 2
        elif depth >= 2:
            score += 1

        article_signals = ('article', 'post', 'story', 'news', 'blog', 'opinion', 'analysis')
        if any(sig in lower_url for sig in article_signals):
            score += 2

        return score

    def _best_link_in(self, element) -> Optional[str]:
        if not hasattr(element, 'find_all'):
            return None

        best_url   = None
        best_score = 0

        for a in element.find_all('a', href=True):
            url  = a['href'].strip()
            if not url.startswith('http'):
                continue
            text = a.get_text(strip=True)
            score = self._score_link(url, text)
            if score > best_score:
                best_score = score
                best_url   = url

        return best_url

    @staticmethod
    def _detect_paywall(text: str) -> bool:
        lower = text.lower()
        return any(phrase in lower for phrase in PAYWALL_PHRASES)
