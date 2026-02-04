"""
Shared API helpers for all Claude modules.

call_claude()  –  drop-in wrapper around client.messages.create()
                  that retries automatically on 429 Rate Limit errors
                  with exponential back-off + jitter.
"""
import time
import random
from typing import Any

from anthropic import Anthropic, RateLimitError

# ── retry tuning ───────────────────────────────────────────────────
MAX_RETRIES     = 5
BASE_DELAY_SECS = 2     # first retry waits ~2 s; doubles each attempt
MAX_DELAY_SECS  = 60    # hard cap — never wait longer than 60 s


def call_claude(client: Anthropic, *, model: str, max_tokens: int,
                messages: list) -> Any:
    """
    Retry-aware wrapper around client.messages.create().

    Catches RateLimitError (HTTP 429), honours the Retry-After header
    when present, and otherwise uses exponential back-off with ±25 %
    jitter.  All other exceptions propagate immediately.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
        except RateLimitError as exc:
            if attempt == MAX_RETRIES:
                print(f"  ✗ Rate-limited {MAX_RETRIES} times in a row — giving up.")
                raise

            # honour Retry-After if available
            retry_after = None
            if hasattr(exc, 'response') and exc.response is not None:
                retry_after = exc.response.headers.get('retry-after')

            if retry_after:
                wait = float(retry_after)
            else:
                wait = min(BASE_DELAY_SECS * (2 ** (attempt - 1)), MAX_DELAY_SECS)

            # ±25 % jitter
            wait *= random.uniform(0.75, 1.25)

            print(f"  ⏳ Rate-limited (attempt {attempt}/{MAX_RETRIES}). "
                  f"Waiting {wait:.1f} s …")
            time.sleep(wait)

    # unreachable, but satisfies type checkers
    raise RuntimeError("call_claude: exhausted retries without result or exception")
