#!/usr/bin/env python3
"""
Newsletter Digest - Setup Script
Guides you through initial setup and configuration
"""
import sys
import os
from pathlib import Path

def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")

def check_dependencies():
    """Check if required packages are installed"""
    print_header("Checking Dependencies")
    
    try:
        import google.auth
        import anthropic
        import bs4
        import jinja2
        print("✓ All Python packages installed")
        return True
    except ImportError as e:
        print(f"✗ Missing packages: {e}")
        print("\nPlease run: pip install -r requirements.txt")
        return False

def setup_env_file():
    """Create .env file from template"""
    print_header("Environment Configuration")
    
    env_file = Path('.env')
    env_example = Path('.env.example')
    
    if env_file.exists():
        print("✓ .env file already exists")
        overwrite = input("  Would you like to reconfigure? (y/N): ").lower()
        if overwrite != 'y':
            return True
    
    print("\nLet's set up your configuration:\n")
    
    # Anthropic API Key
    print("1. Anthropic API Key")
    print("   Get yours at: https://console.anthropic.com/")
    api_key = input("   Enter your Anthropic API key: ").strip()
    
    # Email recipient
    print("\n2. Email Recipient")
    email = input("   Enter your email address (for receiving digests): ").strip()
    
    # GitHub Pages URL (optional)
    print("\n3. GitHub Pages URL (optional, can set up later)")
    print("   Format: https://yourusername.github.io/repository-name")
    github_url = input("   Enter URL (or press Enter to skip): ").strip()
    
    # Write .env file
    with open(env_file, 'w') as f:
        f.write(f"# Newsletter Digest Configuration\n\n")
        f.write(f"ANTHROPIC_API_KEY={api_key}\n")
        f.write(f"DIGEST_EMAIL_RECIPIENT={email}\n")
        if github_url:
            f.write(f"GITHUB_PAGES_URL={github_url}\n")
        else:
            f.write(f"# GITHUB_PAGES_URL=https://yourusername.github.io/newsletter-digest\n")
        f.write(f"\nGMAIL_CREDENTIALS_PATH=credentials.json\n")
        f.write(f"GMAIL_TOKEN_PATH=token.json\n")
    
    print("\n✓ Configuration saved to .env")
    return True

def setup_gmail():
    """Guide user through Gmail API setup"""
    print_header("Gmail API Setup")
    
    credentials_file = Path('credentials.json')
    
    if credentials_file.exists():
        print("✓ credentials.json found")
        return True
    
    print("You need to set up Gmail API access:")
    print("\nSteps:")
    print("1. Go to: https://console.cloud.google.com/")
    print("2. Create a new project (or select existing)")
    print("3. Enable Gmail API:")
    print("   - Search for 'Gmail API'")
    print("   - Click 'Enable'")
    print("4. Create OAuth 2.0 credentials:")
    print("   - Go to 'Credentials' in left menu")
    print("   - Click 'Create Credentials' → 'OAuth client ID'")
    print("   - Application type: 'Desktop app'")
    print("   - Name it: 'Newsletter Digest'")
    print("5. Download the credentials:")
    print("   - Click the download icon")
    print("   - Save as 'credentials.json' in this directory")
    
    print("\n" + "-" * 60)
    input("\nPress Enter once you've downloaded credentials.json...")
    
    if credentials_file.exists():
        print("✓ credentials.json found")
        return True
    else:
        print("✗ credentials.json not found")
        print("Please complete the steps above and try again.")
        return False

def test_gmail_auth():
    """Test Gmail authentication"""
    print_header("Testing Gmail Connection")
    
    try:
        from src.gmail.auth import test_connection
        
        print("This will open a browser window for authentication.")
        print("Please authorize the application to access your Gmail.\n")
        input("Press Enter to continue...")
        
        success = test_connection()
        return success
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    print_header("Creating Directories")
    
    dirs = ['docs', 'email_output', 'src/templates']
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created {dir_path}/")
    
    return True

def main():
    """Run setup wizard"""
    print("\n" + "=" * 60)
    print("  📰 Newsletter Digest - Setup Wizard")
    print("=" * 60)
    
    print("\nThis wizard will help you set up Newsletter Digest.\n")
    
    # Step 1: Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Step 2: Create directories
    create_directories()
    
    # Step 3: Configure .env
    if not setup_env_file():
        sys.exit(1)
    
    # Step 4: Setup Gmail API
    if not setup_gmail():
        print("\nSetup incomplete. Please complete Gmail API setup and run again.")
        sys.exit(1)
    
    # Step 5: Test Gmail authentication
    if not test_gmail_auth():
        print("\nGmail authentication failed. Please check your setup.")
        sys.exit(1)
    
    # Success!
    print_header("Setup Complete! 🎉")
    
    print("Next steps:")
    print("\n1. Test the digest generation:")
    print("   python test_digest.py")
    print("\n2. Run a full digest:")
    print("   python src/main.py")
    print("\n3. Set up automation:")
    print("   See README.md for GitHub Actions or cron setup")
    
    print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    main()
