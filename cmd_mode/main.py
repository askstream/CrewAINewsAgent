"""Точка входа приложения"""
from crew import NewsProcessingCrew
from config import Config
import sys


def main():
    """Основная функция"""
    print("=== CrewAI News Agent ===")
    print()
    print("Настройки LLM:")
    print(f"  Модель: {Config.LLM_MODEL}")
    print(f"  Temperature: {Config.LLM_TEMPERATURE}")
    if Config.OPENAI_API_BASE:
        print(f"  API Endpoint: {Config.OPENAI_API_BASE}")
    else:
        print(f"  API Endpoint: По умолчанию (OpenAI)")
    print()
    print("Настройки обработки:")
    print(f"  Порог схожести для дедупликации: {Config.SIMILARITY_THRESHOLD}")
    print()
    
    # Очистка RSS_FEEDS от пустых строк
    rss_feeds = [feed.strip() for feed in Config.RSS_FEEDS if feed.strip()]
    print(f"RSS каналов: {len(rss_feeds)}")
    if rss_feeds:
        print("RSS каналы:")
        for feed in rss_feeds:
            print(f"  - {feed}")
    
    print(f"Критерий отбора: {Config.SELECTION_CRITERIA}")
    print()
    
    if not Config.OPENAI_API_KEY:
        print("Ошибка: не указан OPENAI_API_KEY в переменных окружения")
        sys.exit(1)
    
    if not rss_feeds:
        print("Ошибка: не указаны RSS_FEEDS в переменных окружения")
        print("Укажите RSS каналы в .env файле через запятую:")
        print("RSS_FEEDS=https://example.com/feed1.xml,https://example.com/feed2.xml")
        sys.exit(1)
    
    if not Config.SELECTION_CRITERIA:
        print("Ошибка: не указан SELECTION_CRITERIA в переменных окружения")
        print("Укажите критерий отбора в .env файле:")
        print("SELECTION_CRITERIA=ваш критерий отбора новостей")
        sys.exit(1)
    
    crew = NewsProcessingCrew()
    crew.process_news(feed_urls=rss_feeds, criteria=Config.SELECTION_CRITERIA)


if __name__ == '__main__':
    main()

