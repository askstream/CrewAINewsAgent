"""Конфигурация приложения с загрузкой переменных из .env"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Класс конфигурации приложения"""
    
    # База данных
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/news_agent.db')
    
    # LLM настройки
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_API_BASE = os.getenv('OPENAI_API_BASE', '')
    LLM_MODEL = os.getenv('LLM_MODEL', 'gpt-4o-mini')
    LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', '0.7'))
    
    # Embedding настройки
    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    
    # RSS каналы (разделенные запятыми)
    RSS_FEEDS = os.getenv('RSS_FEEDS', '').split(',') if os.getenv('RSS_FEEDS') else []
    
    # Критерий отбора новостей
    SELECTION_CRITERIA = os.getenv('SELECTION_CRITERIA', '')
    
    # Настройки дедупликации
    SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.85'))
    
    # Настройки релевантности
    RELEVANCE_THRESHOLD = float(os.getenv('RELEVANCE_THRESHOLD', '0.6'))
    
    # Flask настройки
    FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    FLASK_HOST = os.getenv('FLASK_HOST', '127.0.0.1')
    FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))

