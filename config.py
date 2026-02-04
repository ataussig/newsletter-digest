"""
Central configuration for Newsletter Digest
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "src" / "templates"
DOCS_DIR = BASE_DIR / "docs"
EMAIL_OUTPUT_DIR = BASE_DIR / "email_output"
DATABASE_PATH = BASE_DIR / "newsletter_digest.db"

# Ensure directories exist
DOCS_DIR.mkdir(exist_ok=True)
EMAIL_OUTPUT_DIR.mkdir(exist_ok=True)

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

# Email settings
DIGEST_EMAIL_RECIPIENT = os.getenv("DIGEST_EMAIL_RECIPIENT")

# GitHub Pages URL
GITHUB_PAGES_URL = os.getenv("GITHUB_PAGES_URL", "")

# Gmail API settings
GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "token.json")
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/gmail.send']

# Digest settings
DEFAULT_LOOKBACK_HOURS = 24
MIN_WORD_COUNT = 100  # Minimum words to consider an article

# ---------------------------------------------------------------------------
# Essay newsletters – these are primarily long-form original writing.
# Any article extracted from one of these sources is force-tagged as an essay
# and routed to Claude for summarisation rather than using the newsletter blurb.
# Match is case-insensitive, substring on the newsletter_name field.
# ---------------------------------------------------------------------------
ESSAY_NEWSLETTERS = [
    'stratechery',
    'hanania',          # Richard Hanania
    'clouded judgement',
    'dwarkesh',
]

# Newsletter detection patterns
NEWSLETTER_SERVICES = [
    'substack.com',
    'beehiiv.com',
    'ghost.io',
    'mailchimp.com',
    'sendgrid.net',
    'convertkit.com',
    'revue.com'
]

# ---------------------------------------------------------------------------
# Categories – MECE.  Essays is populated at extraction time (never sent to
# the categorizer).  Other is the catch-all fallback.  The remaining five are
# what the categorizer actually chooses between.
# ---------------------------------------------------------------------------
CATEGORIZABLE_CATEGORIES = [
    'Technology & AI',
    'Business & Finance',
    'Politics & Policy',
    'Science & Health',
    'Culture & Society',
]

# Definitions fed into the categorizer prompt as guardrails.
# One crisp rule per bucket — no overlap.
CATEGORY_DEFINITIONS = {
    'Technology & AI':      'Products, models, tools, platforms — what was built, shipped, or launched. Includes AI companies, software, hardware.',
    'Business & Finance':   'Markets, investing, startups, corporate strategy, M&A, economics, money. Includes Wall Street, venture capital, IPOs.',
    'Politics & Policy':    'Government, regulation, elections, legislation, diplomacy, power. Includes tech regulation, healthcare policy, foreign policy.',
    'Science & Health':     'Research, discoveries, biology, medicine, climate, space, physics. Includes clinical trials, public health, environment.',
    'Culture & Society':    'Media, trends, ideas, social dynamics, consumer behaviour, arts, education. The catch-all for anything that is about people and culture but not politics or business.',
}

# Display order in the digest — Essays first, then the five, then Other.
DIGEST_SECTION_ORDER = [
    'Essays',
] + CATEGORIZABLE_CATEGORIES + [
    'Other',
]
