"""
Database models for Newsletter Digest
Handles all data persistence with comprehensive metadata tracking
"""
import sqlite3
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import config


class Database:
    def __init__(self, db_path: Path = config.DATABASE_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access
        self.create_tables()
    
    def create_tables(self):
        """Create all database tables with comprehensive metadata"""
        cursor = self.conn.cursor()
        
        # Processed emails with full metadata
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_message_id TEXT UNIQUE NOT NULL,
                thread_id TEXT,
                subject TEXT,
                sender_email TEXT,
                sender_name TEXT,
                received_timestamp TEXT,
                processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                raw_headers TEXT,
                is_newsletter BOOLEAN,
                newsletter_service TEXT
            )
        ''')
        
        # Newsletter registry
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS newsletters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_domain TEXT UNIQUE,
                sender_name TEXT,
                category TEXT,
                auto_detected BOOLEAN,
                first_seen TEXT,
                last_seen TEXT,
                total_received INTEGER DEFAULT 0,
                user_whitelisted BOOLEAN DEFAULT 0
            )
        ''')
        
        # Articles with complete metadata
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id INTEGER,
                title TEXT,
                url TEXT,
                author TEXT,
                publish_date TEXT,
                content TEXT,
                content_snippet TEXT,
                word_count INTEGER,
                content_hash TEXT,
                extraction_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                paywall_detected BOOLEAN,
                newsletter_name TEXT,
                newsletter_email TEXT,
                received_timestamp TEXT,
                FOREIGN KEY (email_id) REFERENCES processed_emails(id)
            )
        ''')
        
        # Index for deduplication
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_content_hash 
            ON articles(content_hash)
        ''')
        
        # Article clusters (for duplicate coverage)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS article_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                representative_article_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                digest_date TEXT,
                FOREIGN KEY (representative_article_id) REFERENCES articles(id)
            )
        ''')
        
        # Cluster membership
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_articles (
                cluster_id INTEGER,
                article_id INTEGER,
                similarity_score REAL,
                PRIMARY KEY (cluster_id, article_id),
                FOREIGN KEY (cluster_id) REFERENCES article_clusters(id),
                FOREIGN KEY (article_id) REFERENCES articles(id)
            )
        ''')
        
        # Daily digests
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_digests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                digest_html_path TEXT,
                email_html_path TEXT,
                webpage_url TEXT,
                email_sent BOOLEAN DEFAULT 0,
                email_sent_at TEXT,
                article_count INTEGER,
                newsletter_count INTEGER,
                generation_timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Article appearances in digests
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS digest_articles (
                digest_id INTEGER,
                article_id INTEGER,
                section TEXT,
                importance_score REAL,
                PRIMARY KEY (digest_id, article_id),
                FOREIGN KEY (digest_id) REFERENCES daily_digests(id),
                FOREIGN KEY (article_id) REFERENCES articles(id)
            )
        ''')
        
        self.conn.commit()
    
    def store_email(self, email_data: Dict[str, Any]) -> int:
        """Store processed email with full metadata"""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO processed_emails 
            (gmail_message_id, thread_id, subject, sender_email, sender_name, 
             received_timestamp, raw_headers, is_newsletter, newsletter_service)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            email_data['gmail_message_id'],
            email_data.get('thread_id'),
            email_data['subject'],
            email_data['sender_email'],
            email_data.get('sender_name', ''),
            email_data['received_timestamp'],
            json.dumps(email_data.get('headers', {})),
            email_data['is_newsletter'],
            email_data.get('newsletter_service')
        ))
        
        self.conn.commit()
        
        # Get the ID (either just inserted or existing)
        cursor.execute('''
            SELECT id FROM processed_emails WHERE gmail_message_id = ?
        ''', (email_data['gmail_message_id'],))
        
        result = cursor.fetchone()
        return result['id'] if result else cursor.lastrowid
    
    def store_article(self, article_data: Dict[str, Any], email_id: int) -> int:
        """Store article with full metadata"""
        cursor = self.conn.cursor()
        
        # Generate content hash for deduplication
        content = article_data.get('content', '')
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        cursor.execute('''
            INSERT INTO articles 
            (email_id, title, url, author, publish_date, content, content_snippet,
             word_count, content_hash, paywall_detected, newsletter_name, 
             newsletter_email, received_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            email_id,
            article_data['title'],
            article_data.get('url', ''),
            article_data.get('author'),
            article_data.get('publish_date'),
            content,
            content[:500],  # Snippet for previews
            article_data.get('word_count', 0),
            content_hash,
            article_data.get('paywall_detected', False),
            article_data.get('newsletter_name', ''),
            article_data.get('newsletter_email', ''),
            article_data.get('received_timestamp')
        ))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def get_article_with_metadata(self, article_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve article with ALL metadata"""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT 
                a.*,
                e.gmail_message_id,
                e.sender_email as email_sender,
                e.sender_name,
                e.received_timestamp as email_received
            FROM articles a
            JOIN processed_emails e ON a.email_id = e.id
            WHERE a.id = ?
        ''', (article_id,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def check_if_processed(self, gmail_message_id: str) -> bool:
        """Check if an email has already been processed"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id FROM processed_emails WHERE gmail_message_id = ?
        ''', (gmail_message_id,))
        return cursor.fetchone() is not None
    
    def store_digest(self, digest_data: Dict[str, Any], paths: Dict[str, str]) -> int:
        """Store digest record with paths"""
        cursor = self.conn.cursor()
        
        today = datetime.now().date().isoformat()
        
        cursor.execute('''
            INSERT OR REPLACE INTO daily_digests
            (date, digest_html_path, email_html_path, webpage_url,
             article_count, newsletter_count)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            today,
            paths['webpage_path'],
            paths['email_path'],
            paths.get('webpage_url', ''),
            digest_data['total_articles'],
            digest_data['newsletter_count']
        ))
        
        digest_id = cursor.lastrowid
        
        # Store which articles appeared in this digest
        for article in digest_data.get('all_articles', []):
            cursor.execute('''
                INSERT OR IGNORE INTO digest_articles
                (digest_id, article_id, section, importance_score)
                VALUES (?, ?, ?, ?)
            ''', (
                digest_id,
                article['id'],
                article.get('section', 'categorized'),
                article.get('importance_score', 0)
            ))
        
        self.conn.commit()
        return digest_id
    
    def get_archive_metadata(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get metadata for archive index"""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT * FROM daily_digests
            WHERE date >= date('now', '-' || ? || ' days')
            ORDER BY date DESC
        ''', (days,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_articles(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get articles from the last N hours"""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            SELECT a.*, e.gmail_message_id, e.sender_email, e.sender_name
            FROM articles a
            JOIN processed_emails e ON a.email_id = e.id
            WHERE a.extraction_timestamp >= datetime('now', '-' || ? || ' hours')
            ORDER BY a.extraction_timestamp DESC
        ''', (hours,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def close(self):
        """Close database connection"""
        self.conn.close()
