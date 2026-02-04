"""
Gmail API Authentication
Handles OAuth flow and credential management
"""
import os
import pickle
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import config


def get_gmail_credentials() -> Credentials:
    """
    Get Gmail API credentials, running OAuth flow if needed
    
    This will:
    1. Check for existing token.json (saved credentials)
    2. Refresh if expired
    3. Run OAuth flow if no valid credentials exist
    
    Returns:
        Credentials object for Gmail API
    """
    creds = None
    token_path = Path(config.GMAIL_TOKEN_PATH)
    creds_path = Path(config.GMAIL_CREDENTIALS_PATH)
    
    # Check if we have saved credentials
    if token_path.exists():
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            # Need to run OAuth flow
            if not creds_path.exists():
                raise FileNotFoundError(
                    f"Gmail credentials file not found: {creds_path}\n\n"
                    "Please follow these steps:\n"
                    "1. Go to https://console.cloud.google.com/\n"
                    "2. Create a project (or select existing)\n"
                    "3. Enable Gmail API\n"
                    "4. Create OAuth 2.0 credentials (Desktop app)\n"
                    "5. Download credentials and save as 'credentials.json'\n"
                )
            
            print("Running OAuth flow...")
            print("A browser window will open for Gmail authentication.")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(creds_path), config.GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save credentials for future use
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
        
        print("✓ Gmail credentials saved")
    
    return creds


def test_connection():
    """Test Gmail API connection"""
    try:
        from googleapiclient.discovery import build
        
        creds = get_gmail_credentials()
        service = build('gmail', 'v1', credentials=creds)
        
        # Try to get user profile
        profile = service.users().getProfile(userId='me').execute()
        email = profile.get('emailAddress')
        
        print(f"✓ Successfully connected to Gmail: {email}")
        print(f"✓ Total messages: {profile.get('messagesTotal', 0)}")
        return True
        
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


if __name__ == "__main__":
    # Test the authentication
    print("Testing Gmail API authentication...")
    test_connection()
