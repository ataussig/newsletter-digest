"""
Topic Categorisation via Claude
================================

Only link-based articles come through here.  Essays are hardcoded into the
"Essays" bin at extraction time and never reach the categorizer.

All link articles are sent in a single prompt so the model can see the full
set and make consistent choices.  The prompt includes a one-line definition
for each category (from config.CATEGORY_DEFINITIONS) so Claude has crisp
guardrails — the definitions are what keeps the buckets MECE at runtime.

Returns a plain dict: {article_index: category_string}.
Any index the model omits (or assigns an unrecognised category) falls back
to "Other".
"""
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any

from anthropic import Anthropic

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config
from src.claude.api_helpers import call_claude

SNIPPET_CHARS = 300


class TopicCategorizer:
    def __init__(self, api_key: str = None):
        self.client = Anthropic(api_key=api_key or config.ANTHROPIC_API_KEY)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def categorize_articles(self, articles: List[Dict[str, Any]]) -> Dict[int, str]:
        """
        Assign each article a category.

        Args:
            articles: Link-based articles only (essays already binned).
                      Each needs at least 'title' and 'content'.

        Returns:
            {index: category_string}.  Missing indices → 'Other'.
        """
        if not articles:
            return {}

        prompt = self._build_prompt(articles)

        response = call_claude(
            self.client,
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_map = self._parse_response(response.content[0].text)

        # Fill any missing indices with 'Other'
        return {i: raw_map.get(i, 'Other') for i in range(len(articles))}

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------
    def _build_prompt(self, articles: List[Dict[str, Any]]) -> str:
        # Category list with definitions — this is the guardrail
        cat_lines = "\n".join(
            f"  - {cat}: {config.CATEGORY_DEFINITIONS[cat]}"
            for cat in config.CATEGORIZABLE_CATEGORIES
        )
        cat_lines += "\n  - Other: Use this only when the article genuinely does not fit any of the above."

        # Article snippets
        article_blocks = []
        for i, a in enumerate(articles):
            snippet = (a.get('content') or a.get('blurb') or '')[:SNIPPET_CHARS].replace('\n', ' ')
            article_blocks.append(
                f"[{i}] \"{a.get('title', 'Untitled')}\" "
                f"\u2014 {a.get('newsletter_name', 'Unknown')}\n"
                f"    {snippet}"
            )

        return (
            "Categorize each article into exactly one of the allowed categories.\n"
            "Use the definitions below as strict guardrails — each category has a\n"
            "clear scope.  Only use \"Other\" when the article genuinely does not\n"
            "fit any of the defined categories.\n\n"
            "Allowed categories:\n"
            f"{cat_lines}\n\n"
            "Return ONLY a JSON object mapping each article index (as a string key) "
            "to its category.  No prose, no markdown fences.\n"
            'Example: {"0": "Technology & AI", "1": "Business & Finance"}\n\n'
            "Articles:\n"
            + "\n".join(article_blocks)
        )

    # ------------------------------------------------------------------
    # Parse
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_response(raw: str) -> Dict[int, str]:
        text = raw.strip()
        text = re.sub(r'^```(json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        allowed = set(config.CATEGORIZABLE_CATEGORIES) | {'Other'}

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            print("\u26a0 Categorizer: failed to parse JSON. All articles \u2192 'Other'.")
            return {}

        result: Dict[int, str] = {}
        for key, value in data.items():
            try:
                idx = int(key)
            except (ValueError, TypeError):
                continue
            result[idx] = value if value in allowed else 'Other'

        return result
