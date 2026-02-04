"""
Newsletter Detection
Heuristics to identify and classify newsletters
"""
from typing import Dict, Any, Optional
import re
import config


def is_newsletter(email_data: Dict[str, Any]) -> bool:
    """
    Determine if an email is a newsletter using multiple heuristics
    
    Args:
        email_data: Email data dictionary
        
    Returns:
        True if email appears to be a newsletter
    """
    headers = email_data.get('headers', {})
    subject = email_data.get('subject', '')
    sender_email = email_data.get('sender_email', '')
    html = email_data.get('html', '')
    
    # Heuristic 1: List-Unsubscribe header (strong signal)
    if 'List-Unsubscribe' in headers or 'List-Unsubscribe-Post' in headers:
        return True
    
    # Heuristic 2: Known newsletter services
    newsletter_service = detect_newsletter_service(sender_email, headers)
    if newsletter_service:
        email_data['newsletter_service'] = newsletter_service
        return True
    
    # Heuristic 3: Precedence: bulk header
    if headers.get('Precedence', '').lower() == 'bulk':
        return True
    
    # Heuristic 4: Multiple links + unsubscribe in HTML
    if html and 'unsubscribe' in html.lower():
        link_count = len(re.findall(r'<a\s+(?:[^>]*?\s+)?href=', html, re.IGNORECASE))
        if link_count > 3:
            return True
    
    # Heuristic 5: Common newsletter subject patterns
    newsletter_patterns = [
        r'newsletter',
        r'digest',
        r'weekly\s+update',
        r'daily\s+brief',
        r'this\s+week',
        r'#\d+',  # Issue numbers
    ]
    
    subject_lower = subject.lower()
    for pattern in newsletter_patterns:
        if re.search(pattern, subject_lower):
            return True
    
    # Heuristic 6: Via header (Substack pattern)
    via = headers.get('Via', '')
    if 'substack' in via.lower():
        email_data['newsletter_service'] = 'substack'
        return True
    
    return False


def detect_newsletter_service(sender_email: str, headers: Dict[str, str]) -> Optional[str]:
    """
    Detect which newsletter service sent the email
    
    Args:
        sender_email: Sender email address
        headers: Email headers
        
    Returns:
        Service name if detected, None otherwise
    """
    sender_lower = sender_email.lower()
    
    # Check sender domain
    for service in config.NEWSLETTER_SERVICES:
        if service in sender_lower:
            return service.split('.')[0]
    
    # Check specific headers
    mailer = headers.get('X-Mailer', '').lower()
    if 'substack' in mailer:
        return 'substack'
    if 'beehiiv' in mailer:
        return 'beehiiv'
    
    # Check return-path
    return_path = headers.get('Return-Path', '').lower()
    for service in config.NEWSLETTER_SERVICES:
        if service in return_path:
            return service.split('.')[0]
    
    return None


def extract_newsletter_name(email_data: Dict[str, Any]) -> str:
    """
    Extract the newsletter name from email data
    
    Args:
        email_data: Email data dictionary
        
    Returns:
        Newsletter name (or sender name as fallback)
    """
    # Try sender name first
    sender_name = email_data.get('sender_name', '')
    if sender_name:
        # Clean up common patterns
        sender_name = sender_name.replace(' via Substack', '')
        sender_name = sender_name.replace(' Newsletter', '')
        return sender_name.strip()
    
    # Fallback to subject line parsing
    subject = email_data.get('subject', '')
    
    # Look for patterns like "Newsletter Name - Title"
    if ' - ' in subject:
        parts = subject.split(' - ')
        return parts[0].strip()
    
    # Look for patterns like "Newsletter Name: Title"
    if ': ' in subject:
        parts = subject.split(': ')
        return parts[0].strip()
    
    # Last resort: use email domain
    sender_email = email_data.get('sender_email', '')
    if '@' in sender_email:
        domain = sender_email.split('@')[1]
        return domain.split('.')[0].title()
    
    return 'Unknown Newsletter'


def get_sender_domain(sender_email: str) -> str:
    """
    Extract domain from sender email
    
    Args:
        sender_email: Email address
        
    Returns:
        Domain name
    """
    if '@' in sender_email:
        return sender_email.split('@')[1].lower()
    return ''


def should_skip_email(email_data: Dict[str, Any]) -> bool:
    """
    Determine if email should be skipped (promotional, spam, etc.)
    
    Args:
        email_data: Email data dictionary
        
    Returns:
        True if email should be skipped
    """
    subject = email_data.get('subject', '').lower()
    sender = email_data.get('sender_email', '').lower()
    
    # Skip common promotional senders
    skip_patterns = [
        'noreply',
        'no-reply',
        'donotreply',
        'notifications@',
        'alerts@',
        'digest@google'  # Google Alerts
    ]
    
    for pattern in skip_patterns:
        if pattern in sender:
            return True
    
    # Skip if subject indicates it's not content
    skip_subjects = [
        'verify your',
        'reset password',
        'confirm your',
        'welcome to',
        'receipt',
        'invoice'
    ]
    
    for pattern in skip_subjects:
        if pattern in subject:
            return True
    
    return False
