import os
from dotenv import load_dotenv

# Load environment variables from config.env
load_dotenv('config.env')

class Config:
    """Configuration class for the Okama Finance Bot"""
    
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'okama_finance_bot')

    ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
    
    # YandexGPT Configuration
    YANDEX_API_KEY = os.getenv('YANDEX_API_KEY')
    YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID')
    
    # Okama Configuration
    OKAMA_API_KEY = os.getenv('OKAMA_API_KEY')
    
    # Tushare Configuration
    TUSHARE_API_KEY = os.getenv('TUSHARE_API_KEY')
    
    # Bot Settings
    MAX_MESSAGE_LENGTH = 4096
    MAX_CAPTION_LENGTH = 1024
    
    # Support Configuration
    SUPPORT_GROUP_ID = os.getenv('SUPPORT_GROUP_ID', '-1003121714572')
    SUPPORT_THREAD_ID = os.getenv('SUPPORT_THREAD_ID')  # Optional thread ID
    
    # Botality Analytics Configuration
    BOTALITY_TOKEN = os.getenv('BOTALITY_TOKEN')
    
    # Subscription and Payment Configuration
    SUBSCRIPTION_DB_PATH = os.getenv('SUBSCRIPTION_DB_PATH', 'data/bot.db')
    PRO_PRICE_STARS = int(os.getenv('PRO_PRICE_STARS', '1000'))
    PRO_DURATION_DAYS = int(os.getenv('PRO_DURATION_DAYS', '30'))
    
    # Telegram Stars Payment Mode
    STARS_TEST_MODE = os.getenv('STARS_TEST_MODE', 'false').lower() == 'true'
    
    # Chart Style Configuration
    CHART_STYLE = os.getenv('CHART_STYLE', 'nordic')  # 'nordic' (единственный доступный стиль)
    
    # Supported Commands
    SUPPORTED_COMMANDS = {
        '/start': 'Start the bot and get help',
        '/support': 'Send support request to administrators',
        '/info': 'Show detailed information about an asset',
        '/buy': 'Purchase Pro subscription',
        '/profile': 'View user profile and subscription status'
    }
    
    @classmethod
    def validate(cls):
        """Validate that all required configuration is present"""
        missing = []
        
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append('TELEGRAM_BOT_TOKEN')
        if not cls.YANDEX_API_KEY:
            missing.append('YANDEX_API_KEY')
        if not cls.YANDEX_FOLDER_ID:
            missing.append('YANDEX_FOLDER_ID')
            
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        
        return True
