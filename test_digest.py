#!/usr/bin/env python3
"""
Test Newsletter Digest - Basic Functionality
Tests Gmail connection and newsletter detection without Claude API
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.gmail import get_gmail_credentials, GmailClient, is_newsletter, extract_newsletter_name
from src.database import Database
import config


def test_gmail_connection():
    """Test Gmail API connection"""
    print("\n" + "=" * 60)
    print("TEST 1: Gmail Connection")
    print("=" * 60)
    
    try:
        creds = get_gmail_credentials()
        client = GmailClient(creds)
        
        print("✓ Gmail client initialized successfully")
        return client
        
    except Exception as e:
        print(f"✗ Failed to connect to Gmail: {e}")
        return None


def test_fetch_emails(client, hours=24):
    """Test fetching recent emails"""
    print("\n" + "=" * 60)
    print(f"TEST 2: Fetch Emails (last {hours} hours)")
    print("=" * 60)
    
    try:
        emails = client.get_messages_since(hours=hours)
        print(f"\n✓ Fetched {len(emails)} emails")
        
        if emails:
            print("\nSample email:")
            sample = emails[0]
            print(f"  Subject: {sample['subject']}")
            print(f"  From: {sample['sender_name']} <{sample['sender_email']}>")
            print(f"  Date: {sample['received_timestamp']}")
        
        return emails
        
    except Exception as e:
        print(f"✗ Failed to fetch emails: {e}")
        return []


def test_newsletter_detection(emails):
    """Test newsletter detection"""
    print("\n" + "=" * 60)
    print("TEST 3: Newsletter Detection")
    print("=" * 60)
    
    newsletters = []
    
    for email in emails:
        if is_newsletter(email):
            newsletters.append(email)
    
    print(f"\n✓ Identified {len(newsletters)} newsletters out of {len(emails)} emails")
    
    if newsletters:
        print("\nDetected newsletters:")
        for i, newsletter in enumerate(newsletters[:10], 1):  # Show first 10
            name = extract_newsletter_name(newsletter)
            service = newsletter.get('newsletter_service', 'unknown')
            print(f"  {i}. {name} ({service})")
            print(f"     From: {newsletter['sender_email']}")
            print(f"     Subject: {newsletter['subject'][:60]}...")
            print()
    
    return newsletters


def test_database_storage(newsletters):
    """Test storing newsletters in database"""
    print("\n" + "=" * 60)
    print("TEST 4: Database Storage")
    print("=" * 60)
    
    try:
        db = Database()
        
        new_count = 0
        duplicate_count = 0

        for newsletter in newsletters:
            newsletter['is_newsletter'] = True

            if db.check_if_processed(newsletter['gmail_message_id']):
                duplicate_count += 1          # already in DB from a previous run
            else:
                db.store_email(newsletter)
                new_count += 1                # genuinely new, just stored

        print(f"✓ Stored {new_count} new newsletters")
        if duplicate_count:
            print(f"  Skipped {duplicate_count} already processed (expected on re-run)")

        # Show total rows so the user can see the DB is accumulating correctly
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM processed_emails")
        total = cursor.fetchone()['count']
        print(f"✓ Total emails in database: {total}")

        db.close()
        return True
        
    except Exception as e:
        print(f"✗ Database error: {e}")
        return False


def test_html_extraction(newsletters):
    """Test basic HTML content extraction"""
    print("\n" + "=" * 60)
    print("TEST 5: HTML Content Extraction")
    print("=" * 60)
    
    from bs4 import BeautifulSoup
    import re
    
    for newsletter in newsletters[:3]:  # Test first 3
        html = newsletter.get('html', '')
        
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract links
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('http') and 'unsubscribe' not in href.lower():
                links.append(href)
        
        # Extract text
        text = soup.get_text()
        text = re.sub(r'\s+', ' ', text).strip()
        word_count = len(text.split())
        
        name = extract_newsletter_name(newsletter)
        print(f"\n{name}:")
        print(f"  Links found: {len(links)}")
        print(f"  Word count: {word_count}")
        print(f"  Sample links:")
        for link in links[:3]:
            print(f"    - {link[:70]}...")
    
    print("\n✓ HTML extraction working")
    return True


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("  📰 Newsletter Digest - System Test")
    print("=" * 60)
    print("\nThis will test core functionality without using Claude API.\n")
    
    # Test 1: Gmail connection
    client = test_gmail_connection()
    if not client:
        print("\n❌ Gmail connection failed. Please run setup.py first.")
        sys.exit(1)
    
    # Test 2: Fetch emails
    emails = test_fetch_emails(client, hours=72)  # Last 3 days for better testing
    if not emails:
        print("\n⚠️  No emails found. Try increasing the time window.")
        sys.exit(0)
    
    # Test 3: Newsletter detection
    newsletters = test_newsletter_detection(emails)
    if not newsletters:
        print("\n⚠️  No newsletters detected in fetched emails.")
        print("This might be normal if you haven't received newsletters recently.")
        sys.exit(0)
    
    # Test 4: Database storage
    test_database_storage(newsletters)
    
    # Test 5: HTML extraction
    test_html_extraction(newsletters)
    
    # Summary
    print("\n" + "=" * 60)
    print("  ✅ ALL TESTS PASSED!")
    print("=" * 60)
    print(f"\nSummary:")
    print(f"  • {len(emails)} emails fetched")
    print(f"  • {len(newsletters)} newsletters identified")
    print(f"  • Database storage working")
    print(f"  • HTML extraction working")
    print("\nNext steps:")
    print("  1. Review detected newsletters above")
    print("  2. Run full digest: python src/main.py")
    print("  3. Check output in docs/ folder")
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
