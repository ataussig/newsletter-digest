"""
Essay Summarisation via Claude
================================

This module now has exactly one job: summarise long-form essays.

Link-based articles already have a human-written blurb from the newsletter
author.  That blurb is surfaced directly in the digest — no Claude call.

Essays (detected by the extractor and tagged article_type == 'essay') need
a 2-3 sentence summary because their full text is too long to drop into the
digest inline.  All essays are batched into a single Claude call to stay
well under rate limits.
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

# How much of an essay's body to send to Claude (chars).
# Enough to get the argument; not so much that we burn tokens on boilerplate.
CONTENT_CHARS = 3000


class DigestSummarizer:
    def __init__(self, api_key: str = None):
        self.client = Anthropic(api_key=api_key or config.ANTHROPIC_API_KEY)

    # ==================================================================
    # Public – the only entry point
    # ==================================================================
    def summarize_essays(self, essays: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Produce a 2-3 sentence summary for each essay in ONE API call.

        Args:
            essays: Articles with article_type == 'essay'.  Must have at
                    least 'title', 'content', and 'newsletter_name'.

        Returns:
            The same list of dicts, each with a 'summary' key added.
            If the batch parse fails for any reason every essay gets
            "Summary unavailable." rather than crashing the pipeline.
        """
        if not essays:
            return []

        prompt   = self._build_prompt(essays)
        response = call_claude(
            self.client,
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        summaries = self._parse_response(response.content[0].text, len(essays))

        # Zip onto original dicts (non-destructive copy)
        return [
            {**essay, 'summary': summary}
            for essay, summary in zip(essays, summaries)
        ]

    # ==================================================================
    # Prompt
    # ==================================================================
    @staticmethod
    def _build_prompt(essays: List[Dict[str, Any]]) -> str:
        blocks = []
        for i, e in enumerate(essays):
            content = (e.get('content') or '')[:CONTENT_CHARS]
            blocks.append(
                f"[{i}]\n"
                f"Title : {e.get('title', 'Untitled')}\n"
                f"Source: {e.get('newsletter_name', 'Unknown')}\n"
                f"{content}"
            )

        return (
            "Each of the following is a long-form essay written directly inside\n"
            "a newsletter.  Summarize each one in 2-3 sentences, focusing on\n"
            "the central argument or insight.\n\n"
            "Return ONLY a JSON array of strings, one summary per essay, in the\n"
            "same order as the input.  No keys, no object — just the array.\n"
            "No markdown fences.\n"
            'Example: ["Summary of essay 0.", "Summary of essay 1."]\n\n'
            "Essays:\n\n"
            + "\n\n---\n\n".join(blocks)
        )

    # ==================================================================
    # Parse
    # ==================================================================
    @staticmethod
    def _parse_response(raw: str, expected_count: int) -> List[str]:
        """
        Parse the JSON array.  Falls back to line-splitting if JSON fails
        (Claude occasionally returns numbered paragraphs instead).
        """
        text = raw.strip()
        text = re.sub(r'^```(json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        try:
            data = json.loads(text)
            if isinstance(data, list) and len(data) == expected_count:
                return [str(s).strip() for s in data]
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: numbered lines
        print("  ⚠ Summarizer: batch JSON parse failed, trying line-split fallback.")
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        cleaned = []
        for line in lines:
            line = re.sub(r'^[\[\(]?\d+[\]\).]?\s*', '', line).strip()
            if line:
                cleaned.append(line)

        # Pad or trim to match
        while len(cleaned) < expected_count:
            cleaned.append("Summary unavailable.")
        return cleaned[:expected_count]
