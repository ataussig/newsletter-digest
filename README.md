# 📰 Newsletter Digest

Automated daily newsletter digest that reads your Gmail, identifies newsletters, extracts and categorizes articles, summarizes important content, and delivers a beautiful digest via email + static webpage.

## ✨ Features

- **Smart Newsletter Detection**: Automatically identifies newsletters in your Gmail
- **AI-Powered Deduplication**: Uses Claude to identify when multiple newsletters cover the same story
- **Intelligent Summarization**: Creates concise summaries of top articles
- **Email + Webpage Delivery**: Brief email summary + comprehensive static webpage
- **Archive System**: Searchable history of all past digests
- **Complete Metadata Preservation**: Track original sources for every link

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Gmail account with newsletters
- Anthropic API key ([get one here](https://console.anthropic.com/))
- Google Cloud account (free tier is fine)

### Installation

1. **Clone or download this repository**

```bash
cd newsletter-digest
```

2. **Install dependencies**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Run setup wizard**

```bash
python setup.py
```

The setup wizard will guide you through:
- Creating your `.env` configuration
- Setting up Gmail API access
- Testing your connection

### Gmail API Setup (Detailed)

The setup wizard will guide you, but here are the detailed steps:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the Gmail API:
   - In the search bar, type "Gmail API"
   - Click on "Gmail API"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Application type: **Desktop app**
   - Name: "Newsletter Digest"
   - Click "Create"
5. Download credentials:
   - Click the download icon (⬇) next to your new credential
   - Save the file as `credentials.json` in the project directory

### First Run

After setup, test the digest generation:

```bash
python test_digest.py
```

This will:
- Fetch recent emails (last 24 hours by default)
- Identify newsletters
- Extract articles
- Generate a test digest

## 📖 Usage

### Manual Run

Generate a digest manually:

```bash
python src/main.py
```

This will:
1. Fetch newsletters from last 24 hours
2. Extract and analyze articles
3. Generate webpage in `docs/YYYY-MM-DD.html`
4. Send email summary to your configured address
5. Update the archive index

### Automated Daily Runs

#### Option A: GitHub Actions (Recommended)

1. Create a GitHub repository for your digest
2. Push this code to GitHub
3. Set up GitHub Pages:
   - Go to Settings → Pages
   - Source: Deploy from branch
   - Branch: `main`, folder: `/docs`
4. Add repository secrets:
   - `ANTHROPIC_API_KEY`: Your Claude API key
   - `GMAIL_TOKEN`: Your token.json file (base64 encoded)
   - `DIGEST_EMAIL_RECIPIENT`: Your email
   - `GITHUB_PAGES_URL`: Your GitHub Pages URL

The `.github/workflows/daily_digest.yml` file is already configured to run at 6 AM daily.

#### Option B: Local Cron (Mac/Linux)

Edit your crontab:

```bash
crontab -e
```

Add this line (runs at 6 AM daily):

```
0 6 * * * cd /path/to/newsletter-digest && /path/to/venv/bin/python src/main.py >> logs/digest.log 2>&1
```

## 📁 Project Structure

```
newsletter-digest/
├── src/
│   ├── gmail/              # Gmail API integration
│   │   ├── auth.py         # OAuth authentication
│   │   ├── client.py       # Email fetching
│   │   └── filters.py      # Newsletter detection
│   ├── claude/             # Claude AI integration
│   │   ├── deduplicator.py # Duplicate detection
│   │   ├── categorizer.py  # Topic categorization
│   │   ├── ranker.py       # Importance ranking
│   │   └── summarizer.py   # Content summarization
│   ├── processors/         # Content processing
│   │   └── extractor.py    # Article extraction
│   ├── database/           # Data persistence
│   │   └── models.py       # SQLite schema
│   ├── generator/          # Digest generation
│   │   └── digest.py       # HTML generation
│   └── templates/          # Jinja2 templates
│       ├── email_summary.html
│       ├── digest_webpage.html
│       └── archive_index.html
├── docs/                   # Generated digests (GitHub Pages)
├── config.py              # Configuration
├── setup.py               # Setup wizard
└── requirements.txt       # Python dependencies
```

## ⚙️ Configuration

Edit `.env` to customize:

```bash
# Required
ANTHROPIC_API_KEY=your_key_here
DIGEST_EMAIL_RECIPIENT=your_email@example.com

# Optional
GITHUB_PAGES_URL=https://yourusername.github.io/newsletter-digest
```

Advanced configuration in `config.py`:
- Lookback hours (default: 24)
- Number of featured articles (default: 10)
- Categories
- Newsletter service patterns

## 💰 Cost Estimation

### Claude API Costs
- Model: Claude Sonnet 4.5
- Estimated daily cost: ~$0.90
- Monthly: ~$27

Costs depend on:
- Number of newsletters
- Article length
- Summary complexity

Tips to reduce costs:
- Use Haiku for simpler tasks
- Batch API calls
- Enable prompt caching
- Adjust lookback hours

## 🔧 Troubleshooting

### Gmail Authentication Issues

**Error: "Token expired"**
- Delete `token.json` and run setup again

**Error: "credentials.json not found"**
- Make sure you downloaded OAuth credentials from Google Cloud Console
- Save as `credentials.json` in project root

### No Newsletters Detected

- Check if emails have `List-Unsubscribe` headers
- Verify newsletter services in `config.py`
- Try adjusting detection heuristics in `src/gmail/filters.py`

### Claude API Errors

**Error: "API key not found"**
- Check `.env` file has `ANTHROPIC_API_KEY` set
- Verify key is valid at console.anthropic.com

**Error: "Rate limit exceeded"**
- Reduce number of API calls
- Add delays between requests
- Consider upgrading API tier

## 🎯 Roadmap

Current MVP includes:
- [x] Gmail integration
- [x] Newsletter detection
- [x] Article extraction
- [x] Deduplication (basic)
- [x] Summarization
- [x] Email + webpage delivery
- [x] Archive system
- [x] Metadata preservation

Planned features:
- [ ] Web UI for preferences
- [ ] Advanced deduplication with Claude
- [ ] Personalized ranking
- [ ] Reading time estimates
- [ ] Mobile-optimized views
- [ ] Email threading support
- [ ] Newsletter recommendations

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please feel free to submit a Pull Request.

## 💬 Support

Issues? Questions? Please open an issue on GitHub.

---

Built with ❤️ using Claude Code
