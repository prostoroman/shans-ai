"""
Database service for subscription management
Handles user subscriptions, rate limiting, and payment tracking
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Database configuration
DB_PATH = os.getenv('SUBSCRIPTION_DB_PATH', 'data/bot.db')
DB_DIR = os.path.dirname(DB_PATH)

# Get daily limit from rate limiter configuration
DAILY_TARGET = float(os.getenv("DAILY_TARGET", "30"))

def init_db() -> None:
    """Initialize database with required tables"""
    global DB_PATH, DB_DIR
    try:
        # Ensure directory exists
        try:
            if DB_DIR:
                os.makedirs(DB_DIR, exist_ok=True)
        except PermissionError:
            logger.warning(f"Permission denied creating directory {DB_DIR}. Falling back to local data directory.")
            DB_PATH = 'data/bot.db'
            DB_DIR = os.path.dirname(DB_PATH)
            os.makedirs(DB_DIR, exist_ok=True)
            
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    plan TEXT NOT NULL DEFAULT 'free',
                    requests_today INTEGER NOT NULL DEFAULT 0,
                    last_request TEXT,
                    paid_until TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_plan ON users(plan)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_paid_until ON users(paid_until)')
            
            conn.commit()
            logger.info(f"Database initialized at {DB_PATH}")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

def ensure_user(user_id: int) -> Dict[str, Any]:
    """Ensure user exists in database and return user data"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Check if user exists
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
            
            if user is None:
                # Create new user
                now = datetime.utcnow().isoformat()
                cursor.execute('''
                    INSERT INTO users (user_id, plan, requests_today, last_request, created_at, updated_at)
                    VALUES (?, 'free', 0, ?, ?, ?)
                ''', (user_id, now, now, now))
                conn.commit()
                
                # Return new user data
                return {
                    'user_id': user_id,
                    'plan': 'free',
                    'requests_today': 0,
                    'last_request': now,
                    'paid_until': None,
                    'created_at': now,
                    'updated_at': now
                }
            else:
                # Return existing user data
                return {
                    'user_id': user[0],
                    'plan': user[1],
                    'requests_today': user[2],
                    'last_request': user[3],
                    'paid_until': user[4],
                    'created_at': user[5],
                    'updated_at': user[6]
                }
                
    except Exception as e:
        logger.error(f"Failed to ensure user {user_id}: {e}")
        raise

def can_use(user_id: int, daily_limit: int = None) -> Tuple[bool, Optional[str]]:
    """
    Check if user can make a request
    
    Args:
        user_id: Telegram user ID
        daily_limit: Daily request limit for free users (uses DAILY_TARGET if None)
        
    Returns:
        Tuple of (can_use, error_message_if_denied)
    """
    try:
        user = ensure_user(user_id)
        now = datetime.utcnow()
        
        # Use DAILY_TARGET if no limit specified
        if daily_limit is None:
            daily_limit = int(DAILY_TARGET)
        
        # Check if user is pro and subscription is active
        if user['plan'] == 'pro' and user['paid_until']:
            paid_until = datetime.fromisoformat(user['paid_until'])
            if now < paid_until:
                # Pro user with active subscription - unlimited access
                return True, None
        
        # Check daily limit for free users
        last_request_date = None
        if user['last_request']:
            last_request_date = datetime.fromisoformat(user['last_request']).date()
        
        today = now.date()
        
        # Reset daily counter if it's a new day
        if last_request_date != today:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET requests_today = 0, last_request = ?, updated_at = ?
                    WHERE user_id = ?
                ''', (now.isoformat(), now.isoformat(), user_id))
                conn.commit()
            
            # User can make request (first of the day)
            return True, None
        
        # Check if user has exceeded daily limit
        if user['requests_today'] >= daily_limit:
            return False, f"Достигнут дневной лимит {daily_limit} запросов. Подождите до завтра или купите Pro доступ."
        
        return True, None
        
    except Exception as e:
        logger.error(f"Failed to check user {user_id} access: {e}")
        return False, "Ошибка проверки доступа"

def increment_request_count(user_id: int) -> None:
    """Increment user's request count for today"""
    try:
        now = datetime.utcnow().isoformat()
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET requests_today = requests_today + 1, 
                    last_request = ?, 
                    updated_at = ?
                WHERE user_id = ?
            ''', (now, now, user_id))
            conn.commit()
            
    except Exception as e:
        logger.error(f"Failed to increment request count for user {user_id}: {e}")

def refund_request_count(user_id: int) -> None:
    """Refund user's request count when an error occurs (don't count failed requests)"""
    try:
        now = datetime.utcnow().isoformat()
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Decrement request count, but don't go below 0
            cursor.execute('''
                UPDATE users 
                SET requests_today = MAX(0, requests_today - 1), 
                    updated_at = ?
                WHERE user_id = ? AND requests_today > 0
            ''', (now, user_id))
            conn.commit()
            
        logger.info(f"Refunded request count for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to refund request count for user {user_id}: {e}")

def upgrade_to_pro(user_id: int, days: int = 30) -> bool:
    """
    Upgrade user to pro plan or extend existing subscription
    
    Args:
        user_id: Telegram user ID
        days: Number of days to add to subscription
        
    Returns:
        True if successful, False otherwise
    """
    try:
        now = datetime.utcnow()
        
        # Get current user status
        user = ensure_user(user_id)
        
        # Calculate new paid_until date
        if user['plan'] == 'pro' and user['paid_until']:
            # Extend existing subscription
            current_paid_until = datetime.fromisoformat(user['paid_until'])
            # Only extend if current subscription is still active
            if now < current_paid_until:
                paid_until = current_paid_until + timedelta(days=days)
            else:
                # Subscription expired, start from now
                paid_until = now + timedelta(days=days)
        else:
            # New subscription
            paid_until = now + timedelta(days=days)
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET plan = 'pro', 
                    paid_until = ?, 
                    updated_at = ?
                WHERE user_id = ?
            ''', (paid_until.isoformat(), now.isoformat(), user_id))
            conn.commit()
            
        logger.info(f"User {user_id} upgraded/extended to pro until {paid_until.isoformat()}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to upgrade user {user_id} to pro: {e}")
        return False

def get_user_status(user_id: int, daily_limit: int = None) -> Dict[str, Any]:
    """
    Get user status information
    
    Args:
        user_id: Telegram user ID
        daily_limit: Daily request limit for free users (uses DAILY_TARGET if None)
        
    Returns:
        Dictionary with user status information
    """
    try:
        user = ensure_user(user_id)
        now = datetime.utcnow()
        
        # Use DAILY_TARGET if no limit specified
        if daily_limit is None:
            daily_limit = int(DAILY_TARGET)
        
        # Check if pro subscription is active
        is_pro_active = False
        paid_until_str = None
        
        if user['plan'] == 'pro' and user['paid_until']:
            paid_until = datetime.fromisoformat(user['paid_until'])
            is_pro_active = now < paid_until
            paid_until_str = paid_until.isoformat()
        
        # Calculate remaining requests for free users
        remaining_requests = None
        if user['plan'] == 'free' or not is_pro_active:
            remaining_requests = max(0, daily_limit - user['requests_today'])
        
        return {
            'user_id': user_id,
            'plan': user['plan'],
            'is_pro_active': is_pro_active,
            'requests_today': user['requests_today'],
            'remaining_requests': remaining_requests,
            'daily_limit': daily_limit,
            'paid_until': paid_until_str,
            'last_request': user['last_request']
        }
        
    except Exception as e:
        logger.error(f"Failed to get user status for {user_id}: {e}")
        return {
            'user_id': user_id,
            'plan': 'free',
            'is_pro_active': False,
            'requests_today': 0,
            'remaining_requests': int(DAILY_TARGET),
            'daily_limit': int(DAILY_TARGET),
            'paid_until': None,
            'last_request': None
        }

def cleanup_expired_subscriptions() -> int:
    """
    Clean up expired pro subscriptions
    
    Returns:
        Number of subscriptions cleaned up
    """
    try:
        now = datetime.utcnow().isoformat()
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Find expired pro users
            cursor.execute('''
                SELECT user_id FROM users 
                WHERE plan = 'pro' AND paid_until < ?
            ''', (now,))
            
            expired_users = cursor.fetchall()
            
            if expired_users:
                # Downgrade expired users to free
                cursor.execute('''
                    UPDATE users 
                    SET plan = 'free', 
                        paid_until = NULL, 
                        updated_at = ?
                    WHERE plan = 'pro' AND paid_until < ?
                ''', (now, now))
                conn.commit()
                
                logger.info(f"Cleaned up {len(expired_users)} expired subscriptions")
                return len(expired_users)
            
            return 0
            
    except Exception as e:
        logger.error(f"Failed to cleanup expired subscriptions: {e}")
        return 0
