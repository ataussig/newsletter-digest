"""
Newsletter Digest – Main Orchestrator
======================================

Normal run (daily, triggered by cron or GitHub Actions):
    python src/main.py

Backfill run (seed the archive with older newsletters — one-time use):
    python src/main.py --backfill 30        # last 30 days

Pipeline (7 steps)
------------------
1. Fetch      – pull new emails from Gmail
2. Persist    – store in DB, filter to newsletters only
3. Extract    – pull articles out of each newsletter; each article is
                tagged 'essay' or 'link' at this stage
4. Summarise  – ONE batched Claude call for all essays.
                Link articles skip this entirely — their blurb IS the summary.
5. Categorise – ONE batched Claude call for all link articles.
                Essays are hardcoded into the "Essays" bin.
6. Assemble   – build the digest payload organised by category
7. Render & deliver – Jinja2 → HTML → email (suppressed in backfill mode)

Duplicate guard
---------------
GmailClient.get_messages_since() already skips message IDs that are in
processed_emails.  A second check lives in step 2 as a belt-and-suspenders
measure.
"""
import argparse
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from src.database.models import Database
from src.gmail.auth import get_gmail_credentials
from src.gmail.client import GmailClient
from src.gmail.filters import is_newsletter, should_skip_email, extract_newsletter_name
from src.processors.extractor import ArticleExtractor
from src.claude.categorizer import TopicCategorizer
from src.claude.summarizer import DigestSummarizer
from src.generator.digest import DigestGenerator


class NewsletterDigestApp:
    def __init__(self):
        self.db         = Database()
        self._gmail     = None                   # lazy – see property
        self.extractor  = ArticleExtractor()
        self.categorizer = TopicCategorizer()
        self.summarizer = DigestSummarizer()
        self.generator  = DigestGenerator()

    @property
    def gmail(self) -> GmailClient:
        """Lazy-init so the app can be imported without creds."""
        if self._gmail is None:
            self._gmail = GmailClient(get_gmail_credentials())
        return self._gmail

    # ==================================================================
    # Main entry point
    # ==================================================================
    def run(self, hours_back: int = config.DEFAULT_LOOKBACK_HOURS,
            backfill: bool = False) -> Optional[str]:
        """
        Full pipeline.

        Returns:
            Path to the generated digest HTML, or None if nothing to digest.
        """
        mode_label = f"BACKFILL ({hours_back} h)" if backfill else "DAILY"
        print(f"\n{'=' * 56}")
        print(f"  Newsletter Digest \u2013 {mode_label} run")
        print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 56}\n")

        # ----------------------------------------------------------
        # 1. Fetch
        # ----------------------------------------------------------
        print("\U0001f4e5 Step 1 \u2013 Fetching emails \u2026")
        raw_emails = self.gmail.get_messages_since(hours=hours_back)

        if not raw_emails:
            print("\n\u270b No new emails.  Nothing to do.")
            self.db.close()
            return None

        # ----------------------------------------------------------
        # 2. Persist & newsletter gate
        # ----------------------------------------------------------
        print(f"\n\U0001f4cb Step 2 \u2013 Persisting & filtering newsletters \u2026")
        newsletters: List[Dict[str, Any]] = []
        skipped_dupe  = 0
        skipped_noise = 0

        for email in raw_emails:
            if self.db.check_if_processed(email['gmail_message_id']):
                skipped_dupe += 1
                continue
            if should_skip_email(email):
                skipped_noise += 1
                continue
            if not is_newsletter(email):
                email['is_newsletter'] = False
                self.db.store_email(email)
                continue

            email['is_newsletter'] = True
            self.db.store_email(email)
            newsletters.append(email)

        print(f"  newsletters to process : {len(newsletters)}")
        print(f"  skipped (duplicate)    : {skipped_dupe}")
        print(f"  skipped (noise)        : {skipped_noise}")

        if not newsletters:
            print("\n\u270b No new newsletters found.  Nothing to digest.")
            self.db.close()
            return None

        # ----------------------------------------------------------
        # 3. Extract & classify (essay vs link)
        # ----------------------------------------------------------
        print(f"\n\U0001f4dd Step 3 \u2013 Extracting articles \u2026")
        all_articles: List[Dict[str, Any]] = []

        for nl in newsletters:
            articles = self.extractor.extract_from_email(
                html_content=nl.get('html', ''),
                newsletter_name=extract_newsletter_name(nl),
                newsletter_email=nl.get('sender_email', ''),
                received_timestamp=nl.get('received_timestamp', '')
            )
            email_row_id = self._get_email_row_id(nl['gmail_message_id'])
            for a in articles:
                a['db_id'] = self.db.store_article(a, email_row_id)
            all_articles.extend(articles)

        if not all_articles:
            print("\n\u270b No articles extracted.  Nothing to digest.")
            self.db.close()
            return None

        # Split into the two streams
        essays = [a for a in all_articles if a.get('article_type') == 'essay']
        links  = [a for a in all_articles if a.get('article_type') == 'link']
        print(f"  total articles extracted : {len(all_articles)}")
        print(f"    essays                 : {len(essays)}")
        print(f"    links                  : {len(links)}")

        # ----------------------------------------------------------
        # 4. Summarise essays  (one batched Claude call)
        # ----------------------------------------------------------
        print(f"\n\u270d  Step 4 \u2013 Summarising essays \u2026")
        essays = self.summarizer.summarize_essays(essays)
        print(f"  essays summarised      : {len(essays)}")

        # ----------------------------------------------------------
        # 5. Categorise links  (one batched Claude call)
        # ----------------------------------------------------------
        print(f"\n\U0001f3f7  Step 5 \u2013 Categorising link articles \u2026")
        category_map = self.categorizer.categorize_articles(links)
        # category_map is {index_within_links_list: category_string}

        # ----------------------------------------------------------
        # 6. Assemble digest payload
        # ----------------------------------------------------------
        print(f"\n\U0001f4e6 Step 6 \u2013 Assembling digest \u2026")

        # Build an OrderedDict keyed by DIGEST_SECTION_ORDER.
        # Essays go into their own section; links go into the five
        # categorisable buckets (or Other).
        sections: OrderedDict = OrderedDict()
        for section_name in config.DIGEST_SECTION_ORDER:
            sections[section_name] = []

        # Drop essays into the Essays section
        for essay in essays:
            sections['Essays'].append({
                'title':           essay.get('title', 'Untitled'),
                'url':             essay.get('url', ''),
                'summary':         essay.get('summary', ''),
                'newsletter_name': essay.get('newsletter_name', 'Unknown'),
                'article_type':    'essay',
            })

        # Drop links into their categorised buckets
        for i, link in enumerate(links):
            cat = category_map.get(i, 'Other')
            sections[cat].append({
                'title':           link.get('title', 'Untitled'),
                'url':             link.get('url', ''),
                'blurb':           link.get('blurb', ''),
                'newsletter_name': link.get('newsletter_name', 'Unknown'),
                'article_type':    'link',
            })

        # Strip empty sections so the template doesn't render blank headers
        sections = OrderedDict(
            (k, v) for k, v in sections.items() if v
        )

        digest_data = {
            "date":             datetime.now().strftime('%B %d, %Y'),
            "total_articles":   len(all_articles),
            "newsletter_count": len(newsletters),
            "sections":         sections,   # the single source of truth for the template
        }

        # ----------------------------------------------------------
        # 7. Render & deliver
        # ----------------------------------------------------------
        print(f"\n\U0001f5ea  Step 7 \u2013 Generating HTML \u2026")
        paths = self.generator.generate_and_save(digest_data)
        self.db.store_digest(digest_data, paths)

        if not backfill:
            print(f"\n\U0001f4e7 Sending digest email \u2026")
            self._send_digest(paths['email_path'])
        else:
            print(f"\n\u23ed  Skipped email send (backfill mode)")

        print(f"\n{'=' * 56}")
        print(f"  \u2705 Done!  Digest at: {paths['webpage_path']}")
        print(f"{'=' * 56}\n")

        self.db.close()
        return paths['webpage_path']

    # ==================================================================
    # Email delivery
    # ==================================================================
    def _send_digest(self, html_path: str):
        recipient = config.DIGEST_EMAIL_RECIPIENT
        if not recipient:
            print("  \u26a0 DIGEST_EMAIL_RECIPIENT not set \u2013 skipping send.")
            return

        html_content = Path(html_path).read_text(encoding='utf-8')
        today = datetime.now().strftime('%B %d, %Y')
        subject = f"\U0001f4f0 Your Newsletter Digest \u2013 {today}"

        success = self.gmail.send_email(
            to=recipient,
            subject=subject,
            html_content=html_content
        )

        if success:
            print(f"  \u2713 Digest emailed to {recipient}")
        else:
            print(f"  \u2717 Email send failed \u2013 digest is still saved locally.")

    # ==================================================================
    # Helpers
    # ==================================================================
    def _get_email_row_id(self, gmail_message_id: str) -> int:
        cursor = self.db.conn.cursor()
        cursor.execute(
            'SELECT id FROM processed_emails WHERE gmail_message_id = ?',
            (gmail_message_id,)
        )
        row = cursor.fetchone()
        return row['id'] if row else 0


# ==================================================================
# CLI
# ==================================================================
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Newsletter Digest \u2013 fetch, summarise, categorise, deliver."
    )
    parser.add_argument(
        '--backfill', type=int, default=None, metavar='DAYS',
        help=(
            "Seed the archive with newsletters from the last N days.  "
            "Email delivery is suppressed in this mode.  "
            "Example: --backfill 30"
        )
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    app  = NewsletterDigestApp()

    if args.backfill is not None:
        app.run(hours_back=args.backfill * 24, backfill=True)
    else:
        app.run()
