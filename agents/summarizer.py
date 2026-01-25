"""Агент для генерации саммари новостных статей"""
from config import Config
from models import NewsArticle
from agents.llm_utils import create_llm_with_settings
import requests
import json
import re


def generate_summary_with_direct_api(article: NewsArticle, llm_model: str = None, llm_temperature: float = None) -> str:
    """Генерация саммари через прямой HTTP запрос к API"""
    if not Config.OPENAI_API_KEY:
        return None
    
    if llm_model is None:
        llm_model = Config.LLM_MODEL
    if llm_temperature is None:
        llm_temperature = Config.LLM_TEMPERATURE
    
    # Формируем URL для запроса
    if Config.OPENAI_API_BASE and Config.OPENAI_API_BASE.strip():
        api_url = Config.OPENAI_API_BASE.rstrip('/')
        if not api_url.endswith('/chat/completions'):
            if api_url.endswith('/v1'):
                api_url = f"{api_url}/chat/completions"
            else:
                api_url = f"{api_url}/v1/chat/completions"
    else:
        # Используем стандартный OpenAI endpoint
        api_url = "https://api.openai.com/v1/chat/completions"
    
    # Очищаем HTML из контента для саммари
    content_clean = clean_html(article.content or '')
    
    # Ограничиваем длину контента для экономии токенов
    max_content_length = 2000
    if len(content_clean) > max_content_length:
        content_clean = content_clean[:max_content_length] + "..."
    
    prompt = f"""Создай краткое саммари следующей новости на русском языке (2-3 предложения, максимум 150 слов).

Заголовок: {article.title}
Содержание: {content_clean}

Саммари должно:
- Передавать основную суть новости
- Быть информативным и лаконичным
- Не содержать лишних деталей
- Быть написано на русском языке

Ответь только саммари, без дополнительных пояснений."""
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {Config.OPENAI_API_KEY}'
    }
    
    payload = {
        'model': llm_model,
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'temperature': llm_temperature,
        'max_tokens': 200
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if 'choices' in data and len(data['choices']) > 0:
            summary = data['choices'][0]['message']['content'].strip()
            return summary
        else:
            print(f"Неожиданный формат ответа API: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к API для саммари: {e}")
        return None
    except Exception as e:
        print(f"Ошибка при генерации саммари: {e}")
        return None


def generate_summary_with_langchain(article: NewsArticle, llm_model: str = None, llm_temperature: float = None) -> str:
    """Генерация саммари через LangChain"""
    try:
        from langchain.prompts import ChatPromptTemplate
        from langchain.schema import HumanMessage
        
        llm = create_llm_with_settings(llm_model, llm_temperature)
        
        # Очищаем HTML из контента
        content_clean = clean_html(article.content or '')
        
        # Ограничиваем длину контента
        max_content_length = 2000
        if len(content_clean) > max_content_length:
            content_clean = content_clean[:max_content_length] + "..."
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Ты эксперт по созданию кратких саммари новостей. Создавай информативные и лаконичные саммари на русском языке (2-3 предложения, максимум 150 слов)."),
            ("human", "Заголовок: {title}\n\nСодержание: {content}\n\nСоздай краткое саммари этой новости.")
        ])
        
        messages = prompt.format_messages(
            title=article.title,
            content=content_clean
        )
        
        response = llm.invoke(messages)
        summary = response.content.strip()
        return summary
        
    except Exception as e:
        print(f"Ошибка при генерации саммари через LangChain: {e}")
        return None


def generate_summary(article: NewsArticle, llm_model: str = None, llm_temperature: float = None) -> str:
    """Генерация саммари статьи (автоматический выбор метода)"""
    if not Config.OPENAI_API_KEY:
        print("OPENAI_API_KEY не установлен, используем простое саммари")
        return generate_simple_summary(article)
    
    # Пробуем прямой API запрос
    try:
        summary = generate_summary_with_direct_api(article, llm_model, llm_temperature)
        if summary:
            return summary
    except Exception as e:
        print(f"Ошибка при использовании прямого API для саммари: {e}")
    
    # Fallback на LangChain
    try:
        summary = generate_summary_with_langchain(article, llm_model, llm_temperature)
        if summary:
            return summary
    except Exception as e:
        print(f"Ошибка при использовании LangChain для саммари: {e}")
    
    # Если все методы не сработали, создаем простое саммари из первых предложений
    return generate_simple_summary(article)


def generate_simple_summary(article: NewsArticle) -> str:
    """Простое саммари из первых предложений (fallback)"""
    content = clean_html(article.content or '')
    
    if not content:
        return f"Новость: {article.title}"
    
    # Берем первые 2-3 предложения
    sentences = re.split(r'[.!?]+', content)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) >= 2:
        summary = '. '.join(sentences[:2]) + '.'
        if len(summary) > 200:
            summary = summary[:200] + '...'
        return summary
    elif len(sentences) == 1:
        summary = sentences[0]
        if len(summary) > 200:
            summary = summary[:200] + '...'
        return summary
    else:
        return f"Новость: {article.title}"


def clean_html(text: str) -> str:
    """Очистка HTML тегов из текста"""
    if not text:
        return ''
    
    # Простая очистка HTML тегов
    import re
    # Удаляем HTML теги
    text = re.sub(r'<[^>]+>', '', text)
    # Декодируем HTML entities
    try:
        import html
        text = html.unescape(text)
    except:
        pass
    
    # Удаляем лишние пробелы
    text = ' '.join(text.split())
    return text


def generate_summaries_for_articles(articles: list, llm_model: str = None, llm_temperature: float = None):
    """Генерация саммари для списка статей"""
    from models import get_db_session
    
    session = get_db_session()
    try:
        for article in articles:
            if not article.summary:  # Генерируем только если еще нет саммари
                summary = generate_summary(article, llm_model, llm_temperature)
                if summary:
                    article.summary = summary
                    session.add(article)
        
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Ошибка при сохранении саммари: {e}")
        raise
    finally:
        session.close()
