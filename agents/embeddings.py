"""Модуль для работы с векторными представлениями (embeddings) статей"""
from config import Config
from models import NewsArticle
import requests
import json
import numpy as np
from typing import List, Optional

# Используем модель из конфигурации
EMBEDDING_MODEL = Config.EMBEDDING_MODEL


def generate_embedding_with_openai(text: str, model: str = "text-embedding-3-small") -> Optional[List[float]]:
    """Генерация embedding через OpenAI API или Ollama API"""
    if not text or not text.strip():
        print("Текст для embedding пустой")
        return None
    
    if not Config.OPENAI_API_KEY:
        print("OPENAI_API_KEY не установлен, невозможно сгенерировать embedding")
        return None
    
    # Определяем, используется ли Ollama
    is_ollama = Config.OPENAI_API_BASE and 'localhost:11434' in Config.OPENAI_API_BASE
    
    # Ограничиваем длину текста
    # Для Ollama модели обычно имеют меньший контекст
    if is_ollama:
        max_length = 8000  # Для большинства Ollama embedding моделей
    else:
        max_length = 8000  # Для OpenAI text-embedding-3-small
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
        response = requests.post(api_url, headers=headers, json=payload, timeout=60 if is_ollama else 30)
        response.raise_for_status()
        data = response.json()
        
        if 'data' in data and len(data['data']) > 0:
            embedding = data['data'][0]['embedding']
            return embedding
        else:
            print(f"Неожиданный формат ответа API для embeddings: {data}")
            # Пробуем нативный Ollama API, если OpenAI-совместимый не работает
            if is_ollama:
                return _try_ollama_native_api(text, model)
            return None
    except requests.exceptions.HTTPError as e:
        # Если API не поддерживает embeddings (404), пробуем нативный Ollama API
        if e.response.status_code == 404 and is_ollama:
            print(f"OpenAI-совместимый endpoint не найден, пробуем нативный Ollama API...")
            return _try_ollama_native_api(text, model)
        elif e.response.status_code == 404:
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


def _try_ollama_native_api(text: str, model: str) -> Optional[List[float]]:
    """Попытка использовать нативный Ollama API для embeddings"""
    try:
        ollama_url = "http://localhost:11434/api/embed"
        payload = {
            'model': model,
            'prompt': text
        }
        response = requests.post(ollama_url, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        if 'embedding' in data:
            return data['embedding']
        else:
            print(f"Неожиданный формат ответа Ollama API: {data}")
            return None
    except Exception as e:
        print(f"Ошибка при использовании нативного Ollama API: {e}")
        return None


def generate_embedding_for_article(article: NewsArticle, model: str = None) -> Optional[List[float]]:
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
    if model is None:
        model = EMBEDDING_MODEL
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
        
        # Убеждаемся, что embedding - это список, а не строка JSON
        article_embedding = article.embedding
        if isinstance(article_embedding, str):
            try:
                article_embedding = json.loads(article_embedding)
            except (json.JSONDecodeError, TypeError):
                print(f"Ошибка при десериализации embedding для статьи {article.id}")
                continue
        
        if not isinstance(article_embedding, list):
            print(f"Embedding для статьи {article.id} не является списком: {type(article_embedding)}")
            continue
        
        similarity = cosine_similarity(query_embedding, article_embedding)
        if similarity >= threshold:
            similarities.append((article, similarity))
    
    # Сортируем по убыванию схожести
    similarities.sort(key=lambda x: x[1], reverse=True)
    
    # Возвращаем топ результатов
    return similarities[:limit]


def generate_embeddings_for_articles_by_ids(article_ids: List[int], search_history_id: int = None, model: str = None):
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
                    if model is None:
                        model = EMBEDDING_MODEL
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


def generate_embeddings_for_articles(articles: List[NewsArticle], model: str = None):
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
    """Семантический поиск статей по текстовому запросу с гибридным подходом"""
    from models import get_db_session
    
    # Получаем статьи из базы
    session = get_db_session()
    try:
        query = session.query(NewsArticle).filter(
            NewsArticle.is_duplicate == False
        )
        
        if search_history_id:
            query = query.filter(NewsArticle.search_history_id == search_history_id)
        
        articles = query.all()
        
        if not articles:
            return []
        
        # Гибридный поиск: сначала keyword matching для точных совпадений
        query_lower = query_text.lower().strip()
        query_words_raw = query_lower.split()
        
        # Фильтруем стоп-слова и короткие слова (меньше 2 символов)
        stop_words = {'в', 'на', 'по', 'с', 'из', 'к', 'от', 'до', 'для', 'о', 'об', 'при', 'за', 'под', 'над', 'про', 'со', 'во', 'то', 'как', 'что', 'это', 'или', 'и', 'а', 'но', 'же', 'ли', 'бы', 'был', 'была', 'было', 'были', 'есть', 'быть', 'был', 'быть'}
        query_words = [w for w in query_words_raw if len(w) >= 2 and w not in stop_words]
        total_words = len(query_words)
        
        keyword_matches = []
        keyword_scores = {}
        
        for article in articles:
            title = (str(article.title) if article.title else '').lower()
            content = (str(article.content) if article.content else '').lower()
            summary = (str(article.summary) if article.summary else '').lower()
            
            # Объединяем текст статьи
            article_text = f"{title} {content} {summary}"
            
            # Подсчитываем количество совпадений слов
            matches = 0
            partial_matches = 0
            
            for word in query_words:
                # Точное совпадение
                if word in article_text:
                    matches += 1
                # Частичное совпадение (подстрока)
                elif any(word in article_word or article_word.startswith(word) for article_word in article_text.split()):
                    partial_matches += 1
            
            # Если найдено хотя бы минимальный процент слов или есть частичные совпадения
            if total_words > 0:
                from models import get_setting_float
                min_match_ratio = get_setting_float('keyword_match_min_ratio', 0.5)
                
                match_ratio = matches / total_words
                # Учитываем частичные совпадения с меньшим весом
                partial_ratio = partial_matches / total_words * 0.3
                total_score = match_ratio + partial_ratio
                
                # Добавляем статью если найдено хотя бы минимальный процент слов или есть хорошие совпадения
                if matches >= max(1, int(total_words * min_match_ratio)) or total_score >= 0.4:
                    keyword_scores[article.id] = total_score
                    keyword_matches.append((article, total_score))
        
        # Сортируем keyword matches по убыванию
        keyword_matches.sort(key=lambda x: x[1], reverse=True)
        
        # Теперь семантический поиск для статей с embeddings
        # Это основной механизм поиска - он работает по смыслу, а не по точным словам
        semantic_results = []
        articles_with_embeddings = [a for a in articles if a.embedding]
        
        if articles_with_embeddings:
            # Генерируем embedding для запроса
            query_embedding = generate_embedding_with_openai(query_text, Config.EMBEDDING_MODEL)
            
            if query_embedding:
                # Адаптивный порог в зависимости от длины запроса (из настроек БД)
                from models import get_setting_float
                
                if len(query_words) == 0:
                    semantic_threshold = min(threshold, get_setting_float('semantic_threshold_empty', 0.25))
                elif len(query_words) == 1:
                    semantic_threshold = min(threshold, get_setting_float('semantic_threshold_1_word', 0.3))
                elif len(query_words) == 2:
                    semantic_threshold = min(threshold, get_setting_float('semantic_threshold_2_words', 0.35))
                elif len(query_words) == 3:
                    semantic_threshold = min(threshold, get_setting_float('semantic_threshold_3_words', 0.4))
                elif len(query_words) <= 5:
                    semantic_threshold = min(threshold, get_setting_float('semantic_threshold_4_5_words', 0.5))
                else:
                    semantic_threshold = min(threshold, get_setting_float('semantic_threshold_6_plus_words', 0.6))
                
                print(f"Семантический поиск: запрос '{query_text}' ({len(query_words)} значимых слов), порог: {semantic_threshold}")
                semantic_results = find_similar_articles(query_embedding, articles_with_embeddings, semantic_threshold, limit * 3)
                print(f"Найдено {len(semantic_results)} статей через семантический поиск")
        
        # Объединяем результаты: семантический поиск - основной, keyword matching - дополнительный буст
        # Это позволяет находить статьи по смыслу, даже если слова не совпадают точно
        seen_ids = set()
        results_with_data = []
        
        # Сначала добавляем все semantic results (основной механизм поиска)
        for article, similarity in semantic_results:
            if article.id in seen_ids:
                continue
            seen_ids.add(article.id)
            
            # Если статья также найдена через keyword matching, увеличиваем similarity
            if article.id in keyword_scores:
                keyword_score = keyword_scores[article.id]
                # Комбинируем semantic similarity и keyword score
                # Вес буста берется из настроек БД
                from models import get_setting_float
                boost_weight = get_setting_float('keyword_boost_weight', 0.1)
                similarity = min(1.0, similarity + keyword_score * boost_weight)
            
            try:
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
        
        # Затем добавляем keyword matches, которые не попали в semantic results
        # Это важно для статей без embeddings или с очень низкой semantic similarity
        for article, match_score in keyword_matches[:limit]:
            if article.id in seen_ids:
                continue
            seen_ids.add(article.id)
            
            try:
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
                # Для keyword matches: match_score теперь может быть от 0.4 до 1.0+
                # Если все слова найдены (match_score >= 1.0), это точное совпадение
                if match_score >= 1.0:
                    # Точное совпадение всех слов - высокая similarity (0.95-1.0)
                    # Для однословных запросов используем 0.98-1.0
                    if total_words == 1:
                        similarity = 0.98  # Почти 100% для однословных точных совпадений
                    else:
                        similarity = 0.95 + min((match_score - 1.0) * 0.05, 0.05)
                elif match_score >= 0.8:
                    # Хорошее совпадение (80%+ слов) - высокая similarity
                    similarity = 0.85 + (match_score - 0.8) * 0.5  # От 0.85 до 0.95
                elif match_score >= 0.6:
                    # Среднее совпадение (60%+ слов) - средняя similarity
                    similarity = 0.70 + (match_score - 0.6) * 0.75  # От 0.70 до 0.85
                else:
                    # Частичное совпадение (40-60% слов) - базовая similarity
                    similarity = 0.50 + (match_score - 0.4) * 1.0  # От 0.50 до 0.70
                results_with_data.append((article_data, similarity))
            except Exception as e:
                print(f"Ошибка при получении данных статьи {article.id}: {e}")
                continue
        
        # Добавляем semantic results, исключая дубликаты
        for article, similarity in semantic_results:
            if article.id in seen_ids:
                continue
            seen_ids.add(article.id)
            
            # Если это keyword match, увеличиваем similarity
            if article.id in keyword_scores:
                # Комбинируем keyword score и semantic similarity
                keyword_score = keyword_scores[article.id]
                similarity = max(similarity, keyword_score * 0.5 + similarity * 0.5)
            
            try:
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
        
        # Сортируем все результаты по убыванию similarity
        results_with_data.sort(key=lambda x: x[1], reverse=True)
        
        # Возвращаем топ результатов
        return results_with_data[:limit]
    finally:
        session.close()
