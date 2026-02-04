"""
Gmail API Client
Handles fetching and parsing emails from Gmail
"""
import base64
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
from email.utils import parsedate_to_datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Make sure project root is on path so config and src.database resolve
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config
from src.database.models import Database


class GmailClient:
    def __init__(self, credentials: Credentials):
        self.service = build('gmail', 'v1', credentials=credentials)
    
    def get_messages_since(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Fetch emails from the last N hours that have NOT already been processed.

        Uses the Gmail `after:` query to limit the initial pull to the time
        window, then checks each message ID against the local database before
        making the expensive per-message API call to fetch full content.

        Args:
            hours: Number of hours to look back

        Returns:
            List of email data dictionaries (new messages only)
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        query = f"after:{int(cutoff_time.timestamp())}"

        print(f"Fetching emails since {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}...")

        try:
            # --- Step 1: get the list of message IDs from Gmail --------------
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=500
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                print("No messages found in the specified time range.")
                return []

            print(f"Found {len(messages)} messages in time window.")

            # --- Step 2: filter out already-processed IDs ---------------------
            db = Database()
            new_messages = []
            already_seen = 0

            for msg in messages:
                if db.check_if_processed(msg['id']):
                    already_seen += 1
                else:
                    new_messages.append(msg)

            db.close()

            print(f"  Already processed: {already_seen}")
            print(f"  New (will fetch):  {len(new_messages)}")

            if not new_messages:
                print("Nothing new since last run.")
                return []

            # --- Step 3: fetch full content only for new messages -------------
            emails = []
            for i, message in enumerate(new_messages, 1):
                if i % 10 == 0:
                    print(f"  Fetching message {i}/{len(new_messages)}...")

                email_data = self.get_message_content(message['id'])
                if email_data:
                    emails.append(email_data)

            print(f"✓ Successfully fetched {len(emails)} new emails")
            return emails

        except Exception as e:
            print(f"Error fetching messages: {e}")
            return []
    
    def get_message_content(self, message_id: str) -> Dict[str, Any]:
        """
        Get full content of a specific message
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Dictionary with email data and metadata
        """
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Extract headers
            headers = {h['name']: h['value'] for h in message['payload']['headers']}
            
            # Parse key fields
            email_data = {
                'gmail_message_id': message['id'],
                'thread_id': message['threadId'],
                'subject': headers.get('Subject', ''),
                'sender_email': self._extract_email(headers.get('From', '')),
                'sender_name': self._extract_name(headers.get('From', '')),
                'received_timestamp': self._parse_date(headers.get('Date', '')),
                'headers': headers,
                'html': self._get_html_content(message['payload']),
                'text': self._get_text_content(message['payload'])
            }
            
            return email_data
            
        except Exception as e:
            print(f"Error fetching message {message_id}: {e}")
            return None
    
    def _get_html_content(self, payload: Dict) -> str:
        """Extract HTML content from email payload"""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/html':
                    if 'data' in part['body']:
                        return base64.urlsafe_b64decode(
                            part['body']['data']
                        ).decode('utf-8', errors='ignore')
                
                # Check nested parts
                if 'parts' in part:
                    html = self._get_html_content(part)
                    if html:
                        return html
        
        # Check if body has HTML directly
        if payload.get('mimeType') == 'text/html' and 'data' in payload.get('body', {}):
            return base64.urlsafe_b64decode(
                payload['body']['data']
            ).decode('utf-8', errors='ignore')
        
        return ''
    
    def _get_text_content(self, payload: Dict) -> str:
        """Extract plain text content from email payload"""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        return base64.urlsafe_b64decode(
                            part['body']['data']
                        ).decode('utf-8', errors='ignore')
                
                # Check nested parts
                if 'parts' in part:
                    text = self._get_text_content(part)
                    if text:
                        return text
        
        # Check if body has text directly
        if payload.get('mimeType') == 'text/plain' and 'data' in payload.get('body', {}):
            return base64.urlsafe_b64decode(
                payload['body']['data']
            ).decode('utf-8', errors='ignore')
        
        return ''
    
    def _extract_email(self, from_header: str) -> str:
        """Extract email address from 'From' header"""
        if '<' in from_header and '>' in from_header:
            start = from_header.index('<') + 1
            end = from_header.index('>')
            return from_header[start:end].strip()
        return from_header.strip()
    
    def _extract_name(self, from_header: str) -> str:
        """Extract sender name from 'From' header"""
        if '<' in from_header:
            return from_header.split('<')[0].strip().strip('"')
        return ''
    
    def _parse_date(self, date_str: str) -> str:
        """Parse email date to ISO format"""
        try:
            dt = parsedate_to_datetime(date_str)
            return dt.isoformat()
        except:
            return datetime.now().isoformat()
    
    def send_email(self, to: str, subject: str, html_content: str) -> bool:
        """
        Send an email via Gmail API
        
        Args:
            to: Recipient email address
            subject: Email subject
            html_content: HTML body content
            
        Returns:
            True if sent successfully
        """
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            message = MIMEMultipart('alternative')
            message['To'] = to
            message['Subject'] = subject
            
            html_part = MIMEText(html_content, 'html')
            message.attach(html_part)
            
            raw_message = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode('utf-8')
            
            sent_message = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            print(f"✓ Email sent successfully (ID: {sent_message['id']})")
            return True
            
        except Exception as e:
            print(f"✗ Failed to send email: {e}")
            return False
