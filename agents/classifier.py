"""Агент для классификации новостей по релевантности"""
from crewai import Agent, Task
from langchain_openai import ChatOpenAI
from config import Config
from models import NewsArticle, get_db_session
from typing import List
from agents.llm_utils import create_llm
import requests
import json


def classify_with_direct_api(article: NewsArticle, criteria: str, llm_model: str = None, llm_temperature: float = None, relevance_threshold: float = None) -> dict:
    """Классификация через прямой HTTP запрос к API"""
    if llm_model is None:
        llm_model = Config.LLM_MODEL
    if llm_temperature is None:
        llm_temperature = Config.LLM_TEMPERATURE
    if relevance_threshold is None:
        relevance_threshold = Config.RELEVANCE_THRESHOLD
    
    # Формируем URL для запроса
    api_url = Config.OPENAI_API_BASE.rstrip('/')
    if not api_url.endswith('/chat/completions'):
        if api_url.endswith('/v1'):
            api_url = f"{api_url}/chat/completions"
        else:
            api_url = f"{api_url}/v1/chat/completions"
    
    prompt = f"""Проанализируй следующую новость и определи её релевантность к критерию отбора.

Критерий отбора: {criteria}

Заголовок: {article.title}
Содержание: {article.content[:500] if article.content else 'Нет содержания'}

Ответь в формате JSON:
{{
    "relevance_score": <число от 0.0 до 1.0>,
    "is_relevant": <true или false>,
    "reason": "<краткое объяснение причины>"
}}

Где:
- relevance_score: оценка релевантности (0.0 - не релевантно, 1.0 - полностью релевантно)
- is_relevant: true если relevance_score >= {relevance_threshold}, иначе false
- reason: краткое объяснение почему статья релевантна или нет
"""
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {Config.OPENAI_API_KEY}'
    }
    
    payload = {
        'model': llm_model,
        'messages': [
            {'role': 'user', 'content': prompt}
        ],
        'temperature': llm_temperature
    }
    
    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    
    result = response.json()
    content = result['choices'][0]['message']['content']
    
    # Парсинг JSON из ответа
    import re
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
    if not json_match:
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            json_match = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
    
    if json_match:
        json_str = json_match.group() if hasattr(json_match, 'group') else json_match
        try:
            parsed = json.loads(json_str)
            return {
                'relevance_score': float(parsed.get('relevance_score', 0.0)),
                'is_relevant': bool(parsed.get('is_relevant', False)),
                'reason': parsed.get('reason', '')
            }
        except json.JSONDecodeError:
            pass
    
    # Если не удалось распарсить, используем простую классификацию
    return simple_classification(article, criteria)


def classify_article_relevance(article: NewsArticle, criteria: str) -> dict:
    """Классификация статьи по релевантности с использованием LLM (использует настройки из Config)"""
    return classify_article_relevance_with_settings(article, criteria, Config.LLM_MODEL, Config.LLM_TEMPERATURE, Config.RELEVANCE_THRESHOLD)


def classify_article_relevance_with_settings(article: NewsArticle, criteria: str, llm_model: str = None, llm_temperature: float = None, relevance_threshold: float = None) -> dict:
    """Классификация статьи по релевантности с указанными настройками"""
    if llm_model is None:
        llm_model = Config.LLM_MODEL
    if llm_temperature is None:
        llm_temperature = Config.LLM_TEMPERATURE
    if relevance_threshold is None:
        relevance_threshold = Config.RELEVANCE_THRESHOLD
    
    # Сначала пробуем прямой HTTP запрос, если указан кастомный API
    if Config.OPENAI_API_BASE:
        try:
            return classify_with_direct_api(article, criteria, llm_model, llm_temperature, relevance_threshold)
        except Exception as e:
            print(f"Прямой API запрос не удался: {e}, пробуем через langchain")
    
    # Fallback на langchain
    try:
        llm = create_llm_with_settings(llm_model, llm_temperature)
    except Exception as e:
        print(f"Ошибка при создании LLM: {e}")
        # Fallback на простую классификацию
        return simple_classification(article, criteria, relevance_threshold)
    
    prompt = f"""Проанализируй следующую новость и определи её релевантность к критерию отбора.

Критерий отбора: {criteria}

Заголовок: {article.title}
Содержание: {article.content[:500] if article.content else 'Нет содержания'}

Ответь в формате JSON:
{{
    "relevance_score": <число от 0.0 до 1.0>,
    "is_relevant": <true или false>,
    "reason": "<краткое объяснение причины>"
}}

Где:
- relevance_score: оценка релевантности (0.0 - не релевантно, 1.0 - полностью релевантно)
- is_relevant: true если relevance_score >= {relevance_threshold}, иначе false
- reason: краткое объяснение почему статья релевантна или нет
"""
    
    try:
        # Логирование для отладки
        if Config.OPENAI_API_BASE:
            print(f"Используется API: {Config.OPENAI_API_BASE}, модель: {llm_model}, temperature: {llm_temperature}")
        
        response = llm.invoke(prompt)
        # Парсинг ответа (упрощенный вариант)
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Извлечение JSON из ответа
        import json
        import re
        
        # Улучшенный поиск JSON - ищем вложенные объекты
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if not json_match:
            # Попробуем найти JSON между ```json и ``` или просто между ```
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                json_match = json_match.group(1)
            else:
                # Попробуем найти любой JSON объект
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
        
        if json_match:
            json_str = json_match.group() if hasattr(json_match, 'group') else json_match
            try:
                result = json.loads(json_str)
                return {
                    'relevance_score': float(result.get('relevance_score', 0.0)),
                    'is_relevant': bool(result.get('is_relevant', False)),
                    'reason': result.get('reason', '')
                }
            except json.JSONDecodeError as e:
                print(f"Ошибка парсинга JSON для статьи {article.id}: {e}")
                print(f"Полученный ответ: {content[:200]}")
                return simple_classification(article, criteria)
        else:
            # Fallback: простая оценка по ключевым словам
            print(f"JSON не найден в ответе для статьи {article.id}, используем простую классификацию")
            print(f"Полученный ответ: {content[:200]}")
            return simple_classification(article, criteria)
            
    except Exception as e:
        error_msg = str(e)
        print(f"Ошибка при классификации статьи {article.id}: {error_msg}")
        
        # Детальная информация об ошибке
        if 'Endpoint not supported' in error_msg or '400' in error_msg:
            print(f"Проблема с API endpoint. Проверьте OPENAI_API_BASE: {Config.OPENAI_API_BASE}")
            print(f"Модель: {Config.LLM_MODEL}")
            print("Убедитесь, что base_url указывает на правильный endpoint (без /v1)")
        
        import traceback
        traceback.print_exc()
        return simple_classification(article, criteria)


def simple_classification(article: NewsArticle, criteria: str, relevance_threshold: float = None) -> dict:
    """Простая классификация по ключевым словам (fallback)"""
    if relevance_threshold is None:
        relevance_threshold = Config.RELEVANCE_THRESHOLD
    """Простая классификация на основе ключевых слов (fallback)"""
    text = f"{article.title} {article.content or ''}".lower()
    criteria_lower = criteria.lower()
    
    # Улучшенная обработка: удаляем стоп-слова и знаки препинания
    import string
    # Удаляем знаки препинания
    text_clean = text.translate(str.maketrans('', '', string.punctuation))
    criteria_clean = criteria_lower.translate(str.maketrans('', '', string.punctuation))
    
    # Разбиваем на слова и фильтруем короткие слова (меньше 3 символов)
    criteria_words = set([w for w in criteria_clean.split() if len(w) >= 3])
    text_words = set([w for w in text_clean.split() if len(w) >= 3])
    
    matches = len(criteria_words.intersection(text_words))
    total_words = len(criteria_words)
    
    # Также проверяем частичные совпадения (подстроки)
    partial_matches = 0
    for crit_word in criteria_words:
        if any(crit_word in text_word or text_word in crit_word for text_word in text_words):
            partial_matches += 1
    
    # Комбинируем точные и частичные совпадения
    if total_words == 0:
        score = 0.0
    else:
        # Вес точных совпадений выше
        exact_score = matches / total_words
        partial_score = partial_matches / total_words * 0.5
        score = min(exact_score + partial_score, 1.0)
    
    return {
        'relevance_score': score,
        'is_relevant': score >= relevance_threshold,
        'reason': f'Простая классификация: {matches} точных совпадений, {partial_matches} частичных из {total_words} ключевых слов'
    }


def classify_articles(articles: List[NewsArticle], criteria: str):
    """Классификация списка статей (использует настройки из Config)"""
    classify_articles_with_settings(articles, criteria, Config.LLM_MODEL, Config.LLM_TEMPERATURE, Config.RELEVANCE_THRESHOLD)


def classify_articles_with_settings(articles: List[NewsArticle], criteria: str, llm_model: str = None, llm_temperature: float = None, relevance_threshold: float = None):
    """Классификация списка статей с указанными настройками"""
    if llm_model is None:
        llm_model = Config.LLM_MODEL
    if llm_temperature is None:
        llm_temperature = Config.LLM_TEMPERATURE
    if relevance_threshold is None:
        relevance_threshold = Config.RELEVANCE_THRESHOLD
    
    session = get_db_session()
    
    try:
        for article in articles:
            if article.is_duplicate:
                continue  # Пропускаем дубликаты
            
            result = classify_article_relevance_with_settings(article, criteria, llm_model, llm_temperature, relevance_threshold)
            
            article.relevance_score = result['relevance_score']
            article.is_relevant = result['is_relevant']
            article.classification_reason = result['reason']
            
            session.merge(article)
        
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Ошибка при классификации: {e}")
    finally:
        session.close()


def create_classifier_agent() -> Agent:
    """Создание агента для классификации"""
    llm = create_llm()
    
    return Agent(
        role='News Classifier',
        goal='Классифицировать новости по релевантности к заданному критерию отбора',
        backstory='Ты опытный аналитик новостей, который умеет определять релевантность '
                 'статей к заданным критериям. Ты внимательно анализируешь содержание '
                 'и даешь объективную оценку.',
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

