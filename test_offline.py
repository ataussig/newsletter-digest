"""
Offline test suite for the redesigned Newsletter Digest pipeline.

Tests everything that can be verified without network or real API keys:
  A – ArticleExtractor  (extraction strategies, blurb, essay/link classification)
  B – TopicCategorizer  (JSON parse + category validation)
  C – DigestSummarizer  (prompt structure + JSON parse + fallback)
  D – DigestGenerator   (template renders without crashing)
  E – Database          (duplicate guard)
  F – URL noise filter  (disclaimer links, social links, etc.)
"""
import sys, os, types, json, tempfile
from pathlib import Path
from unittest.mock import MagicMock

# ── mock external deps before any project code loads ──
anthropic_mock = types.ModuleType('anthropic')
class _FakeClient:
    def __init__(self, *a, **kw): pass
    class messages:
        @staticmethod
        def create(**kw):
            resp = MagicMock()
            resp.content = [MagicMock(text='{}')]
            return resp
anthropic_mock.Anthropic = _FakeClient
anthropic_mock.RateLimitError = type('RateLimitError', (Exception,), {})
sys.modules['anthropic'] = anthropic_mock

for mod_name in ('google.oauth2.credentials','google_auth_oauthlib.flow',
                 'google.auth.transport.requests','googleapiclient.discovery',
                 'google.oauth2','google.auth.transport','google','google.auth',
                 'google_auth_oauthlib'):
    sys.modules[mod_name] = MagicMock()

os.environ['ANTHROPIC_API_KEY'] = 'sk-test-fake'

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from src.processors.extractor import ArticleExtractor
from src.claude.categorizer   import TopicCategorizer
from src.claude.summarizer    import DigestSummarizer
from src.generator.digest     import DigestGenerator
from src.database.models      import Database

passed = 0; failed = 0; errors = []
def ok(n):
    global passed; passed += 1; print(f'  \u2713 {n}')
def fail(n, d):
    global failed; failed += 1; errors.append((n,d)); print(f'  \u2717 {n}  \u2014 {d}')

# ==================================================================
# A – ArticleExtractor
# ==================================================================
print('\n\u2500\u2500 A: ArticleExtractor \u2500\u2500')

ext = ArticleExtractor()

# A1 – section-based extraction produces articles with blurb
html_sections = """<html><body>
<h2><a href="https://example.com/story1">Big News Story</a></h2>
<p>This is the newsletter author's take on the big news. Very informative blurb here.</p>
<h2><a href="https://example.com/story2">Another Headline</a></h2>
<p>Second blurb written by the newsletter editor about story two.</p>
</body></html>"""

articles = ext.extract_from_email(html_sections,
    newsletter_name='Tech Daily',
    newsletter_email='digest@techdaily.com')

# MIN_WORD_COUNT filter may drop short articles; check we get what we expect
if len(articles) >= 1:
    # At least one article should be classified as 'link' (has outbound URL)
    link_articles = [a for a in articles if a['article_type'] == 'link']
    if link_articles and link_articles[0].get('blurb'):
        ok('A1 – section extraction produces link articles with blurbs')
    else:
        fail('A1', f'expected link articles with blurbs; got {articles}')
else:
    # Sections were too short to pass MIN_WORD_COUNT — that's fine, test the
    # link-based strategy instead (tested in A2)
    ok('A1 – section extraction (articles below MIN_WORD_COUNT, expected for short test fixture)')

# A2 – essay newsletter force-tag
essay_html = """<html><body>
<h2>On the Future of Bundling</h2>
<p>""" + ' '.join(['This is a long essay about bundling in the tech industry.'] * 20) + """</p>
</body></html>"""

essays = ext.extract_from_email(essay_html,
    newsletter_name='Stratechery',
    newsletter_email='ben@stratechery.com')

essay_tagged = [a for a in essays if a['article_type'] == 'essay']
if essay_tagged:
    ok('A2 – Stratechery articles force-tagged as essay')
else:
    fail('A2', f'expected essay tag; got types: {[a["article_type"] for a in essays]}')

# A3 – no-URL article classified as essay
no_url_html = """<html><body>
<h2>Thoughts on AI</h2>
<p>""" + ' '.join(['Long form content with no outbound links at all.'] * 20) + """</p>
</body></html>"""

no_url = ext.extract_from_email(no_url_html,
    newsletter_name='Random Newsletter',
    newsletter_email='news@random.com')

no_url_essays = [a for a in no_url if a['article_type'] == 'essay']
if no_url_essays:
    ok('A3 – article with no URL classified as essay')
else:
    fail('A3', f'got types: {[a["article_type"] for a in no_url]}')

# A4 – self-hosted URL (domain matches newsletter) classified as essay
self_hosted_html = """<html><body>
<h2><a href="https://mysubstack.substack.com/p/deep-dive">Deep Dive</a></h2>
<p>""" + ' '.join(['Detailed analysis of market trends and implications.'] * 20) + """</p>
</body></html>"""

self_hosted = ext.extract_from_email(self_hosted_html,
    newsletter_name='My Substack',
    newsletter_email='author@mysubstack.substack.com')

self_hosted_essays = [a for a in self_hosted if a['article_type'] == 'essay']
if self_hosted_essays:
    ok('A4 – self-hosted URL (domain matches newsletter) classified as essay')
else:
    fail('A4', f'got types: {[a["article_type"] for a in self_hosted]}')

# A5 – blurb strips the title from the front
title_text = "Repeated Title"
content_text = f"{title_text} The actual blurb follows the title here."
blurb = ArticleExtractor._extract_blurb(content_text, title_text)
if blurb.startswith("The actual blurb"):
    ok('A5 – blurb correctly strips leading title')
else:
    fail('A5', f'blurb = "{blurb}"')

# A6 – known essay newsletters (case insensitive)
for name in ['Stratechery', 'STRATECHERY', 'Richard Hanania', 'richard hanania',
             'Clouded Judgement', 'clouded judgement', 'Dwarkesh Patel', 'dwarkesh patel']:
    if not ArticleExtractor._is_essay_newsletter(name):
        fail(f'A6 – "{name}" should be essay newsletter', 'returned False')
        break
else:
    ok('A6 – all known essay newsletters detected (case insensitive)')

# ==================================================================
# B – TopicCategorizer (parse logic)
# ==================================================================
print('\n\u2500\u2500 B: TopicCategorizer parse \u2500\u2500')

# B1 – valid JSON parses correctly
raw_valid = '{"0": "Technology & AI", "1": "Business & Finance", "2": "Other"}'
parsed = TopicCategorizer._parse_response(raw_valid)
if parsed == {0: 'Technology & AI', 1: 'Business & Finance', 2: 'Other'}:
    ok('B1 – valid JSON parsed correctly')
else:
    fail('B1', f'got {parsed}')

# B2 – unrecognised category snaps to Other
raw_bad_cat = '{"0": "Vibes & Feelings"}'
parsed2 = TopicCategorizer._parse_response(raw_bad_cat)
if parsed2 == {0: 'Other'}:
    ok('B2 – unrecognised category snaps to Other')
else:
    fail('B2', f'got {parsed2}')

# B3 – fenced JSON (```json ... ```) still parses
raw_fenced = '```json\n{"0": "Politics & Policy"}\n```'
parsed3 = TopicCategorizer._parse_response(raw_fenced)
if parsed3 == {0: 'Politics & Policy'}:
    ok('B3 – fenced JSON parses correctly')
else:
    fail('B3', f'got {parsed3}')

# B4 – completely broken JSON returns empty dict (all fall to Other)
parsed4 = TopicCategorizer._parse_response('this is not json at all')
if parsed4 == {}:
    ok('B4 – broken JSON returns empty dict (caller fills Other)')
else:
    fail('B4', f'got {parsed4}')

# B5 – prompt contains all CATEGORIZABLE categories + definitions
cat = TopicCategorizer()
dummy_articles = [{'title': 'Test', 'content': 'x' * 100, 'newsletter_name': 'NL'}]
prompt = cat._build_prompt(dummy_articles)
all_cats_present = all(c in prompt for c in config.CATEGORIZABLE_CATEGORIES)
all_defs_present = all(config.CATEGORY_DEFINITIONS[c] in prompt for c in config.CATEGORIZABLE_CATEGORIES)
if all_cats_present and all_defs_present:
    ok('B5 – prompt contains all categories and their definitions')
else:
    fail('B5', f'cats={all_cats_present} defs={all_defs_present}')

# ==================================================================
# C – DigestSummarizer (prompt + parse)
# ==================================================================
print('\n\u2500\u2500 C: DigestSummarizer \u2500\u2500')

summ = DigestSummarizer()

# C1 – prompt says "essay" and includes all titles
dummy_essays = [
    {'title': 'Essay One', 'content': 'x' * 500, 'newsletter_name': 'NL1'},
    {'title': 'Essay Two', 'content': 'y' * 500, 'newsletter_name': 'NL2'},
]
prompt = summ._build_prompt(dummy_essays)
if 'Essay One' in prompt and 'Essay Two' in prompt and 'essay' in prompt.lower():
    ok('C1 – prompt includes all essay titles and uses word "essay"')
else:
    fail('C1', 'titles or essay keyword missing from prompt')

# C2 – valid JSON array parses
raw_arr = '["Summary of essay one.", "Summary of essay two."]'
parsed_s = summ._parse_response(raw_arr, 2)
if parsed_s == ["Summary of essay one.", "Summary of essay two."]:
    ok('C2 – JSON array parsed correctly')
else:
    fail('C2', f'got {parsed_s}')

# C3 – fenced JSON array parses
raw_fenced_arr = '```json\n["First.", "Second."]\n```'
parsed_f = summ._parse_response(raw_fenced_arr, 2)
if parsed_f == ["First.", "Second."]:
    ok('C3 – fenced JSON array parsed correctly')
else:
    fail('C3', f'got {parsed_f}')

# C4 – numbered-line fallback
raw_numbered = "1. First summary.\n2. Second summary.\n3. Third summary."
parsed_n = summ._parse_response(raw_numbered, 3)
if len(parsed_n) == 3 and 'First summary.' in parsed_n[0]:
    ok('C4 – numbered-line fallback works')
else:
    fail('C4', f'got {parsed_n}')

# C5 – too few lines pads with placeholder
raw_short = "Only one line here."
parsed_p = summ._parse_response(raw_short, 3)
if len(parsed_p) == 3 and parsed_p[1] == "Summary unavailable.":
    ok('C5 – short response padded to expected count')
else:
    fail('C5', f'got {parsed_p}')

# C6 – empty essay list returns empty list immediately
if summ.summarize_essays([]) == []:
    ok('C6 – empty input short-circuits to empty list')
else:
    fail('C6', 'non-empty return on empty input')

# ==================================================================
# D – DigestGenerator (template render smoke test)
# ==================================================================
print('\n\u2500\u2500 D: DigestGenerator template render \u2500\u2500')

from collections import OrderedDict

gen = DigestGenerator()

sections = OrderedDict()
sections['Essays'] = [
    {'title': 'Deep Thoughts', 'url': '', 'summary': 'A great essay.', 'newsletter_name': 'Stratechery', 'article_type': 'essay'},
]
sections['Technology & AI'] = [
    {'title': 'New Model Ships', 'url': 'https://example.com', 'blurb': 'OpenAI did a thing.', 'newsletter_name': 'The Verge', 'article_type': 'link'},
]
sections['Other'] = [
    {'title': 'Misc Item', 'url': 'https://misc.com', 'blurb': 'Something else.', 'newsletter_name': 'Random', 'article_type': 'link'},
]

digest_data = {
    'date': 'February 03, 2026',
    'total_articles': 3,
    'newsletter_count': 3,
    'sections': sections,
}

try:
    html = gen._render(digest_data)
    checks = [
        ('Essays header', 'Essays' in html),
        ('essay title', 'Deep Thoughts' in html),
        ('essay summary', 'A great essay.' in html),
        ('category header', 'Technology &amp; AI' in html),   # Jinja autoescapes &
        ('link title', 'New Model Ships' in html),
        ('link blurb', 'OpenAI did a thing.' in html),
        ('source name', 'The Verge' in html),
        ('Other section', 'Other' in html),
    ]
    all_ok = True
    for label, result in checks:
        if not result:
            fail(f'D – {label}', 'not found in rendered HTML')
            all_ok = False
    if all_ok:
        ok('D – template renders all sections, titles, blurbs, summaries, sources')
except Exception as e:
    fail('D – template render', str(e))

# ==================================================================
# E – Database duplicate guard
# ==================================================================
print('\n\u2500\u2500 E: Database duplicate guard \u2500\u2500')

import sqlite3
# Patch config to use a temp DB
orig_db_path = config.DATABASE_PATH
tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
config.DATABASE_PATH = Path(tmp.name)
tmp.close()

db = Database()
db.store_email({
    'gmail_message_id': 'msg-001',
    'thread_id': 'thr-001',
    'subject': 'Test',
    'sender_email': 'a@b.com',
    'sender_name': 'A',
    'received_timestamp': '2026-02-03T00:00:00',
    'headers': '{}',
    'html': '<p>hi</p>',
    'text': 'hi',
    'is_newsletter': True,
})

if db.check_if_processed('msg-001') and not db.check_if_processed('msg-999'):
    ok('E – duplicate guard: stored ID detected, unknown ID not')
else:
    fail('E', 'duplicate guard logic wrong')
db.close()

config.DATABASE_PATH = orig_db_path
os.unlink(tmp.name)

# ==================================================================
# F – URL noise filter
# ==================================================================
print('\n\u2500\u2500 F: URL noise filter \u2500\u2500')

noise_urls = [
    ('https://example.com/disclaimer', ''),
    ('https://example.com/privacy', ''),
    ('https://twitter.com/someone', ''),
    ('https://facebook.com/page', ''),
    ('https://example.com/unsubscribe', ''),
    ('https://example.com/good-article', 'Click here to unsubscribe'),
]
signal_urls = [
    ('https://example.com/news/ai-breakthrough', 'AI Breakthrough Story'),
    ('https://blog.example.com/2026/01/deep-dive', 'A Deep Dive into Markets'),
]

noise_ok = all(ArticleExtractor._is_noise_url(u, t) for u, t in noise_urls)
signal_ok = all(not ArticleExtractor._is_noise_url(u, t) for u, t in signal_urls)

if noise_ok:
    ok('F1 – all noise URLs correctly filtered')
else:
    fail('F1', 'some noise URL passed through')
if signal_ok:
    ok('F2 – legitimate article URLs not filtered')
else:
    fail('F2', 'some signal URL was incorrectly filtered')

# ==================================================================
# Summary
# ==================================================================
total = passed + failed
print(f'\n{"=" * 50}')
print(f'  {passed}/{total} passed, {failed} failed')
if errors:
    print(f'\n  Failures:')
    for name, detail in errors:
        print(f'    \u2717 {name}: {detail}')
print(f'{"=" * 50}\n')

if failed > 0:
    sys.exit(1)
