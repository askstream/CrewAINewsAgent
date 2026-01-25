"""Модуль для работы с векторными представлениями (embeddings) статей"""
from config import Config
from models import NewsArticle
import requests
import json
import numpy as np
from typing import List, Optional


def generate_embedding_with_openai(text: str, model: str = "text-embedding-3-small") -> Optional[List[float]]:
    """Генерация embedding через OpenAI API"""
    if not text or not text.strip():
        print("Текст для embedding пустой")
        return None
    
    if not Config.OPENAI_API_KEY:
        print("OPENAI_API_KEY не установлен, невозможно сгенерировать embedding")
        return None
    
    # Ограничиваем длину текста (максимум 8000 токенов для text-embedding-3-small)
    max_length = 8000
    text = text[:max_length] if len(text) > max_length else text
    
    # Формируем URL для запроса
    if Config.OPENAI_API_BASE and Config.OPENAI_API_BASE.strip():
        api_url = Config.OPENAI_API_BASE.rstrip('/')
        if not api_url.endswith('/embeddings'):
            if api_url.endswith('/v1'):
                api_url = f"{api_url}/embeddings"
            else:
                api_url = f"{api_url}/v1/embeddings"
    else:
        # Используем стандартный OpenAI endpoint
        api_url = "https://api.openai.com/v1/embeddings"
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {Config.OPENAI_API_KEY}'
    }
    
    payload = {
        'model': model,
        'input': text
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if 'data' in data and len(data['data']) > 0:
            embedding = data['data'][0]['embedding']
            return embedding
        else:
            print(f"Неожиданный формат ответа API для embeddings: {data}")
            return None
    except requests.exceptions.HTTPError as e:
        # Если API не поддерживает embeddings (404), просто пропускаем
        if e.response.status_code == 404:
            print(f"API endpoint для embeddings не найден (404). Embeddings будут пропущены.")
            return None
        print(f"HTTP ошибка при запросе к API для embeddings: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе к API для embeddings: {e}")
        return None
    except Exception as e:
        print(f"Ошибка при генерации embedding: {e}")
        return None


def generate_embedding_for_article(article: NewsArticle, model: str = "text-embedding-3-small") -> Optional[List[float]]:
    """Генерация embedding для статьи"""
    # Получаем значения атрибутов напрямую, чтобы избежать проблем с сессией
    try:
        title = article.title if hasattr(article, 'title') else None
        content = article.content if hasattr(article, 'content') else None
    except Exception as e:
        # Если объект не привязан к сессии, пытаемся получить значения через getattr
        print(f"Ошибка при доступе к атрибутам статьи: {e}")
        title = getattr(article, 'title', None)
        content = getattr(article, 'content', None)
    
    # Комбинируем заголовок и содержание для лучшего представления
    text_parts = []
    
    if title:
        text_parts.append(str(title))
    
    if content:
        # Очищаем HTML и берем первые 2000 символов
        content_clean = clean_text(str(content))
        if content_clean:
            text_parts.append(content_clean[:2000])
    
    if not text_parts:
        return None
    
    combined_text = " ".join(text_parts)
    return generate_embedding_with_openai(combined_text, model)


def clean_text(text: str) -> str:
    """Очистка текста от HTML и лишних символов"""
    if not text:
        return ''
    
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


def cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """Вычисление косинусного сходства между двумя векторами"""
    if not embedding1 or not embedding2:
        return 0.0
    
    if len(embedding1) != len(embedding2):
        return 0.0
    
    try:
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        return float(similarity)
    except Exception as e:
        print(f"Ошибка при вычислении косинусного сходства: {e}")
        return 0.0


def find_similar_articles(query_embedding: List[float], articles: List[NewsArticle], 
                         threshold: float = 0.7, limit: int = 10) -> List[tuple]:
    """Поиск похожих статей по embedding"""
    if not query_embedding:
        return []
    
    similarities = []
    
    for article in articles:
        if not article.embedding:
            continue
        
        similarity = cosine_similarity(query_embedding, article.embedding)
        if similarity >= threshold:
            similarities.append((article, similarity))
    
    # Сортируем по убыванию схожести
    similarities.sort(key=lambda x: x[1], reverse=True)
    
    # Возвращаем топ результатов
    return similarities[:limit]


def generate_embeddings_for_articles_by_ids(article_ids: List[int], search_history_id: int = None, model: str = "text-embedding-3-small"):
    """Генерация embeddings для списка статей по их ID"""
    from models import get_db_session
    
    if not article_ids:
        return
    
    session = get_db_session()
    try:
        processed_count = 0
        for article_id in article_ids:
            # Загружаем статью из текущей сессии
            db_article = session.query(NewsArticle).filter_by(id=article_id).first()
            if not db_article:
                print(f"Статья {article_id} не найдена в БД, пропускаем")
                continue
            
            # Дополнительная фильтрация по search_history_id, если указана
            if search_history_id and db_article.search_history_id != search_history_id:
                continue
                
            # Генерируем только если еще нет embedding
            if not db_article.embedding:
                # Получаем значения атрибутов сразу после загрузки, чтобы избежать проблем с сессией
                try:
                    article_title = str(db_article.title) if db_article.title else ''
                    article_content = str(db_article.content) if db_article.content else ''
                    print(f"Генерация embedding для статьи {db_article.id}: {article_title[:50] if article_title else 'Без заголовка'}...")
                except Exception as e:
                    print(f"Ошибка при получении атрибутов статьи {db_article.id}: {e}")
                    continue
                
                # Генерируем embedding, передавая значения напрямую
                text_parts = []
                if article_title:
                    text_parts.append(article_title)
                if article_content:
                    content_clean = clean_text(article_content)
                    if content_clean:
                        text_parts.append(content_clean[:2000])
                
                if text_parts:
                    combined_text = " ".join(text_parts)
                    embedding = generate_embedding_with_openai(combined_text, model)
                    if embedding:
                        db_article.embedding = embedding
                        processed_count += 1
                        print(f"Embedding сгенерирован для статьи {db_article.id} (размер: {len(embedding)})")
                    else:
                        print(f"Не удалось сгенерировать embedding для статьи {db_article.id}")
                else:
                    print(f"Нет текста для генерации embedding для статьи {db_article.id}")
            else:
                print(f"Статья {db_article.id} уже имеет embedding, пропускаем")
        
        if processed_count > 0:
            session.commit()
            print(f"Сохранено {processed_count} embeddings в БД")
        else:
            print("Нет новых embeddings для сохранения")
    except Exception as e:
        session.rollback()
        print(f"Ошибка при сохранении embeddings: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


def generate_embeddings_for_articles(articles: List[NewsArticle], model: str = "text-embedding-3-small"):
    """Генерация embeddings для списка статей (устаревший метод, используйте generate_embeddings_for_articles_by_ids)"""
    # Получаем ID статей до того, как они станут detached
    article_ids = []
    for article in articles:
        try:
            article_ids.append(article.id)
        except Exception as e:
            print(f"Ошибка при получении ID статьи: {e}")
            continue
    
    # Используем новую функцию с ID
    return generate_embeddings_for_articles_by_ids(article_ids, None, model)


def semantic_search(query_text: str, search_history_id: int = None, 
                   threshold: float = 0.7, limit: int = 20) -> List[tuple]:
    """Семантический поиск статей по текстовому запросу"""
    from models import get_db_session
    
    # Генерируем embedding для запроса
    query_embedding = generate_embedding_with_openai(query_text)
    if not query_embedding:
        return []
    
    # Получаем статьи из базы
    session = get_db_session()
    try:
        query = session.query(NewsArticle).filter(
            NewsArticle.is_duplicate == False,
            NewsArticle.embedding.isnot(None)
        )
        
        if search_history_id:
            query = query.filter(NewsArticle.search_history_id == search_history_id)
        
        articles = query.all()
        
        # Ищем похожие статьи
        results = find_similar_articles(query_embedding, articles, threshold, limit)
        
        # Получаем значения атрибутов до закрытия сессии, чтобы избежать проблем
        # Создаем список кортежей (статья, similarity, данные)
        results_with_data = []
        for article, similarity in results:
            try:
                # Получаем все нужные атрибуты сразу, пока сессия открыта
                article_data = {
                    'id': article.id,
                    'title': str(article.title) if article.title else '',
                    'content': str(article.content) if article.content else '',
                    'summary': str(article.summary) if article.summary else '',
                    'link': str(article.link) if article.link else '',
                    'source': str(article.source) if article.source else 'Неизвестный источник',
                    'published_at': article.published_at.isoformat() if article.published_at else None,
                    'relevance_score': article.relevance_score,
                    'is_relevant': article.is_relevant,
                    'classification_reason': str(article.classification_reason) if article.classification_reason else ''
                }
                results_with_data.append((article_data, similarity))
            except Exception as e:
                print(f"Ошибка при получении данных статьи {article.id}: {e}")
                continue
        
        return results_with_data
    finally:
        session.close()
