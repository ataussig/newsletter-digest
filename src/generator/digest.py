"""
Digest HTML Generation
========================

Takes the structured data assembled by main.py and renders it through the
Jinja2 template.  Writes two identical copies to disk:

  email_output/<date>_digest.html   – the copy that gets mailed
  docs/<date>_digest.html           – archive copy (e.g. served via GitHub Pages)
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config


class DigestGenerator:
    def __init__(self):
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(config.TEMPLATES_DIR)),
            autoescape=True          # safe for email HTML
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def generate_and_save(self, digest_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Render and write both output files.

        Args:
            digest_data: Dict with keys:
                • date               (str)
                • total_articles     (int)
                • newsletter_count   (int)
                • sections           (OrderedDict: section_name -> list of article dicts)

        Returns:
            {"email_path": str, "webpage_path": str}
        """
        html = self._render(digest_data)

        today = datetime.now().strftime('%Y-%m-%d')

        email_path   = config.EMAIL_OUTPUT_DIR / f"{today}_digest.html"
        webpage_path = config.DOCS_DIR        / f"{today}_digest.html"

        email_path.write_text(html, encoding='utf-8')
        webpage_path.write_text(html, encoding='utf-8')

        print(f"  \u2713 Digest written to {email_path}")
        print(f"  \u2713 Archive copy at  {webpage_path}")

        return {
            "email_path":   str(email_path),
            "webpage_path": str(webpage_path)
        }

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _render(self, digest_data: Dict[str, Any]) -> str:
        template = self.jinja_env.get_template('digest_template.html')
        return template.render(
            date=digest_data.get('date', datetime.now().strftime('%B %d, %Y')),
            total_articles=digest_data.get('total_articles', 0),
            newsletter_count=digest_data.get('newsletter_count', 0),
            sections=digest_data.get('sections', {}),
        )
