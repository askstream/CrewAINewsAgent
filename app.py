"""Flask веб-приложение для управления обработкой новостей"""
from flask import Flask, render_template, request, jsonify
from threading import Thread
import uuid
import time
from datetime import datetime
from sqlalchemy import func
from config import Config
from models import NewsArticle, SearchHistory, SystemSettings, get_db_session, init_db, engine, get_all_settings, get_setting, update_setting

app = Flask(__name__)
app.secret_key = Config.FLASK_SECRET_KEY

# Инициализация БД при импорте модуля
init_db()

# Хранилище статусов задач
tasks_status = {}


@app.errorhandler(500)
def internal_error(error):
    """Обработчик внутренних ошибок - всегда возвращает JSON"""
    return jsonify({
        'success': False,
        'error': 'Внутренняя ошибка сервера'
    }), 500


@app.errorhandler(404)
def not_found(error):
    """Обработчик 404 - всегда возвращает JSON"""
    return jsonify({
        'success': False,
        'error': 'Ресурс не найден'
    }), 404


class ProgressTracker:
    """Класс для отслеживания прогресса выполнения"""
    
    def __init__(self, task_id):
        self.task_id = task_id
        self.status = 'pending'  # pending, running, completed, error
        self.current_step = 0
        self.total_steps = 5
        self.steps = [
            {'name': 'Сбор новостей из RSS каналов', 'status': 'pending', 'progress': 0, 'message': ''},
            {'name': 'Дедупликация статей', 'status': 'pending', 'progress': 0, 'message': ''},
            {'name': 'Классификация по релевантности', 'status': 'pending', 'progress': 0, 'message': ''},
            {'name': 'Генерация саммари статей', 'status': 'pending', 'progress': 0, 'message': ''},
            {'name': 'Генерация векторных представлений', 'status': 'pending', 'progress': 0, 'message': ''}
        ]
        self.error_message = ''
        self.statistics = {}
        self.search_history_id = None
    
    def update_step(self, step_index, status, progress=0, message=''):
        """Обновление статуса шага"""
        if 0 <= step_index < len(self.steps):
            self.steps[step_index]['status'] = status
            self.steps[step_index]['progress'] = progress
            self.steps[step_index]['message'] = message
            self.current_step = step_index
    
    def to_dict(self):
        """Преобразование в словарь для JSON"""
        return {
            'task_id': self.task_id,
            'status': self.status,
            'current_step': self.current_step,
            'total_steps': self.total_steps,
            'steps': self.steps,
            'error_message': self.error_message,
            'statistics': self.statistics,
            'search_history_id': self.search_history_id
        }


def process_news_with_progress(task_id, feed_urls, criteria, llm_model=None, llm_temperature=None, similarity_threshold=None, relevance_threshold=None, openai_api_base=None):
    """Обработка новостей с отслеживанием прогресса"""
    tracker = tasks_status[task_id]
    
    # Использование переданных параметров или значений по умолчанию
    if llm_model is None:
        llm_model = Config.LLM_MODEL
    if llm_temperature is None:
        llm_temperature = Config.LLM_TEMPERATURE
    if similarity_threshold is None:
        similarity_threshold = Config.SIMILARITY_THRESHOLD
    if relevance_threshold is None:
        relevance_threshold = Config.RELEVANCE_THRESHOLD
        similarity_threshold = Config.SIMILARITY_THRESHOLD
    if openai_api_base is None:
        openai_api_base = Config.OPENAI_API_BASE
    
    # Импорты в начале функции
    from agents.rss_collector import collect_rss_news
    from agents.deduplicator import find_duplicates, mark_duplicates
    from agents.classifier import classify_articles_with_settings
    from models import get_db_session  # Явный импорт для избежания проблем с областью видимости
    import json
    
    search_history_id = None
    
    try:
        tracker.status = 'running'
        
        # Инициализация БД
        init_db()
        
        # Создание записи истории запроса
        session = get_db_session()
        try:
            search_history = SearchHistory(
                rss_feeds='\n'.join(feed_urls),
                selection_criteria=criteria,
                llm_model=llm_model,
                llm_temperature=llm_temperature,
                similarity_threshold=similarity_threshold,
                openai_api_base=openai_api_base or '',
                results_data={
                    'relevance_threshold': relevance_threshold
                }
            )
            session.add(search_history)
            session.commit()
            search_history_id = search_history.id
            tracker.search_history_id = search_history_id
        except Exception as e:
            session.rollback()
            print(f"Ошибка при создании истории запроса: {e}")
            import traceback
            traceback.print_exc()
            # Продолжаем работу даже если не удалось создать историю
        finally:
            session.close()
        
        # Шаг 1: Сбор новостей
        tracker.update_step(0, 'running', 0, 'Начало сбора новостей...')
        
        articles = collect_rss_news(feed_urls)
        tracker.update_step(0, 'running', 50, f'Собрано {len(articles)} статей')
        
        if articles:
            session = get_db_session()
            try:
                saved_count = 0
                for article in articles:
                    # Проверяем, не существует ли уже эта статья в текущем запросе
                    existing = session.query(NewsArticle).filter(
                        NewsArticle.link == article.link,
                        NewsArticle.search_history_id == search_history_id
                    ).first()
                    
                    if existing:
                        continue  # Пропускаем, если уже есть в этом запросе
                    
                    article.search_history_id = search_history_id
                    session.add(article)
                    saved_count += 1
                
                session.commit()
                tracker.update_step(0, 'completed', 100, f'Сохранено {saved_count} новых статей (из {len(articles)} собранных)')
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()
        else:
            tracker.update_step(0, 'completed', 100, 'Новых новостей не найдено')
        
        # Получение необработанных статей для текущего запроса
        session = get_db_session()
        try:
            unprocessed_articles = session.query(NewsArticle).filter(
                NewsArticle.search_history_id == search_history_id,
                NewsArticle.is_duplicate == False,
                NewsArticle.relevance_score == None
            ).all()
        finally:
            session.close()
        
        if not unprocessed_articles:
            tracker.status = 'completed'
            tracker.statistics = {'message': 'Нет статей для обработки'}
            return
        
        # Шаг 2: Дедупликация
        tracker.update_step(1, 'running', 0, f'Анализ {len(unprocessed_articles)} статей...')
        
        duplicates = find_duplicates(unprocessed_articles, similarity_threshold, search_history_id)
        tracker.update_step(1, 'running', 50, f'Найдено {len(duplicates)} дубликатов')
        
        if duplicates:
            mark_duplicates(unprocessed_articles, duplicates)
            tracker.update_step(1, 'completed', 100, f'Помечено {len(duplicates)} дубликатов')
        else:
            tracker.update_step(1, 'completed', 100, 'Дубликаты не найдены')
        
        # Получение уникальных статей для текущего запроса
        session = get_db_session()
        try:
            unique_articles = session.query(NewsArticle).filter(
                NewsArticle.search_history_id == search_history_id,
                NewsArticle.is_duplicate == False,
                NewsArticle.relevance_score == None
            ).all()
            # Получаем ID статей до закрытия сессии
            unique_article_ids = [article.id for article in unique_articles]
        finally:
            session.close()
        
        # Шаг 3: Классификация
        if not criteria:
            tracker.update_step(2, 'error', 0, 'Критерий отбора не указан')
            tracker.status = 'error'
            tracker.error_message = 'Критерий отбора не указан'
            return
        
        print(f"Критерий отбора: {criteria}")
        print(f"Используемые настройки: модель={llm_model}, temperature={llm_temperature}, порог схожести={similarity_threshold}, порог релевантности={relevance_threshold}")
        tracker.update_step(2, 'running', 0, f'Классификация {len(unique_articles)} статей по критерию: {criteria[:50]}...')
        
        total = len(unique_articles)
        for i, article in enumerate(unique_articles):
            classify_articles_with_settings([article], criteria, llm_model, llm_temperature, relevance_threshold)
            progress = int((i + 1) / total * 100)
            tracker.update_step(2, 'running', progress, f'Обработано {i + 1} из {total} статей')
        
        tracker.update_step(2, 'completed', 100, f'Классифицировано {total} статей')
        
        # Шаг 4: Генерация саммари для релевантных статей (опционально)
        # Загружаем релевантные статьи заново из БД
        session = get_db_session()
        try:
            relevant_articles = session.query(NewsArticle).filter(
                NewsArticle.search_history_id == search_history_id,
                NewsArticle.is_duplicate == False,
                NewsArticle.is_relevant == True
            ).all()
        finally:
            session.close()
            
        if relevant_articles:
            try:
                from agents.summarizer import generate_summaries_for_articles
                tracker.update_step(3, 'running', 0, f'Генерация саммари для {len(relevant_articles)} релевантных статей...')
                generate_summaries_for_articles(relevant_articles, llm_model, llm_temperature)
                tracker.update_step(3, 'completed', 100, f'Саммари сгенерировано для {len(relevant_articles)} статей')
            except Exception as e:
                print(f"Ошибка при генерации саммари: {e}")
                import traceback
                traceback.print_exc()
                tracker.update_step(3, 'error', 0, f'Ошибка при генерации саммари: {str(e)[:50]}')
                # Продолжаем работу даже если саммари не удалось сгенерировать
        else:
            tracker.update_step(3, 'completed', 100, 'Нет релевантных статей для генерации саммари')
        
        # Шаг 5: Генерация embeddings для всех уникальных статей (опционально)
        try:
            from agents.embeddings import generate_embeddings_for_articles_by_ids
            tracker.update_step(4, 'running', 0, f'Генерация векторных представлений для {len(unique_article_ids)} статей...')
            generate_embeddings_for_articles_by_ids(unique_article_ids, search_history_id)
            tracker.update_step(4, 'completed', 100, f'Векторные представления сгенерированы для {len(unique_articles)} статей')
        except Exception as e:
            print(f"Ошибка при генерации embeddings: {e}")
            import traceback
            traceback.print_exc()
            tracker.update_step(4, 'error', 0, f'Ошибка при генерации embeddings: {str(e)[:50]}')
            # Продолжаем работу даже если embeddings не удалось сгенерировать
        
        # Итоговая статистика для текущего запроса
        session = get_db_session()
        try:
            total_count = session.query(NewsArticle).filter(
                NewsArticle.search_history_id == search_history_id
            ).count()
            relevant = session.query(NewsArticle).filter(
                NewsArticle.search_history_id == search_history_id,
                NewsArticle.is_relevant == True,
                NewsArticle.is_duplicate == False
            ).count()
            duplicates_count = session.query(NewsArticle).filter(
                NewsArticle.search_history_id == search_history_id,
                NewsArticle.is_duplicate == True
            ).count()
            unique_non_relevant = total_count - relevant - duplicates_count
            
            tracker.statistics = {
                'total': total_count,
                'relevant': relevant,
                'duplicates': duplicates_count,
                'unique_non_relevant': unique_non_relevant
            }
            
            # Обновление истории запроса с результатами
            if search_history_id:
                search_history = session.query(SearchHistory).filter_by(id=search_history_id).first()
                if search_history:
                    search_history.results_data = {
                        'total': total_count,
                        'relevant': relevant,
                        'duplicates': duplicates_count,
                        'unique_non_relevant': unique_non_relevant,
                        'collected_articles': len(articles) if articles else 0,
                        'processed_articles': len(unique_articles)
                    }
                    session.commit()
        finally:
            session.close()
        
        tracker.status = 'completed'
        tracker.search_history_id = search_history_id
        
    except Exception as e:
        tracker.status = 'error'
        tracker.error_message = str(e)
        import traceback
        print(f"Ошибка при обработке: {traceback.format_exc()}")


@app.route('/')
def index():
    """Главная страница с формой"""
    # Передаем настройки в шаблон
    settings = {
        'llm_model': Config.LLM_MODEL,
        'llm_temperature': Config.LLM_TEMPERATURE,
        'similarity_threshold': Config.SIMILARITY_THRESHOLD,
        'relevance_threshold': Config.RELEVANCE_THRESHOLD,
        'openai_api_base': Config.OPENAI_API_BASE if Config.OPENAI_API_BASE else 'По умолчанию (OpenAI)',
        'rss_feeds': '\n'.join(Config.RSS_FEEDS) if Config.RSS_FEEDS else '',
        'selection_criteria': Config.SELECTION_CRITERIA if Config.SELECTION_CRITERIA else ''
    }
    return render_template('index.html', settings=settings)


@app.route('/api/start', methods=['POST'])
def start_processing():
    """Запуск обработки новостей"""
    data = request.json
    
    feed_urls = [url.strip() for url in data.get('rss_feeds', '').split('\n') if url.strip()]
    criteria = data.get('criteria', '').strip()
    
    # Получение настроек из формы или использование значений по умолчанию
    llm_model = data.get('llm_model', '').strip() or Config.LLM_MODEL
    llm_temperature = float(data.get('llm_temperature', Config.LLM_TEMPERATURE))
    similarity_threshold = float(data.get('similarity_threshold', Config.SIMILARITY_THRESHOLD))
    relevance_threshold = float(data.get('relevance_threshold', Config.RELEVANCE_THRESHOLD))
    # API Endpoint берется из конфигурации, не из формы
    openai_api_base = Config.OPENAI_API_BASE or ''
    
    if not feed_urls:
        return jsonify({'error': 'Не указаны RSS каналы'}), 400
    
    if not criteria:
        return jsonify({'error': 'Не указан критерий отбора'}), 400
    
    # Валидация параметров
    if not (0 <= llm_temperature <= 2):
        return jsonify({'error': 'Temperature должен быть от 0.0 до 2.0'}), 400
    
    if not (0 <= similarity_threshold <= 1):
        return jsonify({'error': 'Порог схожести должен быть от 0.0 до 1.0'}), 400
    
    if not (0 <= relevance_threshold <= 1):
        return jsonify({'error': 'Порог релевантности должен быть от 0.0 до 1.0'}), 400
    
    # Создание задачи
    task_id = str(uuid.uuid4())
    tracker = ProgressTracker(task_id)
    tasks_status[task_id] = tracker
    
    # Запуск обработки в отдельном потоке с настройками
    thread = Thread(target=process_news_with_progress, args=(task_id, feed_urls, criteria, llm_model, llm_temperature, similarity_threshold, relevance_threshold, openai_api_base))
    thread.daemon = True
    thread.start()
    
    return jsonify({'task_id': task_id})


@app.route('/api/status/<task_id>')
def get_status(task_id):
    """Получение статуса задачи"""
    if task_id not in tasks_status:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    return jsonify(tasks_status[task_id].to_dict())


@app.route('/api/results')
def get_results():
    """Получение результатов обработки (для текущего запроса или всех)"""
    try:
        search_history_id = request.args.get('search_history_id', type=int)
        
        session = get_db_session()
        try:
            query = session.query(NewsArticle).filter(
                NewsArticle.is_duplicate == False
            )
            
            # Фильтрация по истории запроса, если указана
            if search_history_id:
                query = query.filter(NewsArticle.search_history_id == search_history_id)
            
            # Сортировка: сначала по релевантности, затем по свежести запроса, затем по дате публикации
            from sqlalchemy import desc, nullslast
            articles = query.order_by(
                desc(NewsArticle.is_relevant),  # Релевантные вверху
                desc(NewsArticle.search_history_id),  # Свежие запросы вверху
                nullslast(desc(NewsArticle.published_at)),  # Свежие новости вверху
                desc(NewsArticle.collected_at)
            ).all()
            
            results = []
            for article in articles:
                try:
                    # Безопасное получение summary и embedding (на случай, если колонки еще не добавлены в БД)
                    summary = getattr(article, 'summary', None) or ''
                    embedding = getattr(article, 'embedding', None)
                    
                    results.append({
                        'id': article.id,
                        'title': article.title,
                        'content': article.content or '',
                        'summary': summary,
                        'link': article.link,
                        'source': article.source or 'Неизвестный источник',
                        'published_at': article.published_at.isoformat() if article.published_at else None,
                        'relevance_score': article.relevance_score,
                        'is_relevant': article.is_relevant,
                        'classification_reason': article.classification_reason or '',
                        'search_history_id': article.search_history_id
                    })
                except Exception as e:
                    # Если возникла ошибка при доступе к полям, пропускаем эту статью
                    print(f"Ошибка при обработке статьи {article.id}: {e}")
                    continue
            
            return jsonify({'articles': results})
        except Exception as e:
            import traceback
            print(f"Ошибка в /api/results: {traceback.format_exc()}")
            return jsonify({'error': str(e), 'articles': []}), 500
        finally:
            session.close()
    except Exception as e:
        import traceback
        print(f"Ошибка в /api/results: {traceback.format_exc()}")
        return jsonify({'error': str(e), 'articles': []}), 500


@app.route('/api/search-history')
def get_search_history():
    """Получение истории запросов с пагинацией"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 5
        
        session = get_db_session()
        try:
            total = session.query(SearchHistory).count()
            history = session.query(SearchHistory).order_by(
                SearchHistory.created_at.desc()
            ).offset((page - 1) * per_page).limit(per_page).all()
            
            results = []
            for record in history:
                results.append({
                    'id': record.id,
                    'created_at': record.created_at.isoformat() if record.created_at else None,
                    'rss_feeds': record.rss_feeds,
                    'selection_criteria': record.selection_criteria,
                    'llm_model': record.llm_model,
                    'llm_temperature': record.llm_temperature,
                    'similarity_threshold': record.similarity_threshold,
                    'openai_api_base': record.openai_api_base,
                    'results_data': record.results_data or {}
                })
            
            return jsonify({
                'history': results,
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page
            })
        except Exception as e:
            import traceback
            print(f"Ошибка в /api/search-history: {traceback.format_exc()}")
            return jsonify({'error': str(e), 'history': [], 'total': 0, 'page': page, 'per_page': per_page, 'total_pages': 0}), 500
        finally:
            session.close()
    except Exception as e:
        import traceback
        print(f"Ошибка в /api/search-history: {traceback.format_exc()}")
        return jsonify({'error': str(e), 'history': [], 'total': 0, 'page': 1, 'per_page': 5, 'total_pages': 0}), 500


@app.route('/api/search-history/<int:history_id>/articles')
def get_history_articles(history_id):
    """Получение статей для конкретной истории запроса"""
    try:
        session = get_db_session()
        try:
            # Сортировка: сначала по релевантности, затем по дате публикации
            from sqlalchemy import desc, nullslast
            articles = session.query(NewsArticle).filter(
                NewsArticle.search_history_id == history_id,
                NewsArticle.is_duplicate == False
            ).order_by(
                desc(NewsArticle.is_relevant),  # Релевантные вверху
                nullslast(desc(NewsArticle.published_at)),  # Свежие новости вверху
                desc(NewsArticle.collected_at)
            ).all()
            
            results = []
            for article in articles:
                try:
                    # Безопасное получение summary (на случай, если колонка еще не добавлена в БД)
                    summary = getattr(article, 'summary', None) or ''
                    
                    results.append({
                        'id': article.id,
                        'title': article.title,
                        'content': article.content or '',
                        'summary': summary,
                        'link': article.link,
                        'source': article.source or 'Неизвестный источник',
                        'published_at': article.published_at.isoformat() if article.published_at else None,
                        'relevance_score': article.relevance_score,
                        'is_relevant': article.is_relevant,
                        'classification_reason': article.classification_reason or ''
                    })
                except Exception as e:
                    # Если возникла ошибка при доступе к полям, пропускаем эту статью
                    print(f"Ошибка при обработке статьи {article.id}: {e}")
                    continue
            
            return jsonify({'articles': results})
        except Exception as e:
            import traceback
            print(f"Ошибка в /api/search-history/{history_id}/articles: {traceback.format_exc()}")
            return jsonify({'error': str(e), 'articles': []}), 500
        finally:
            session.close()
    except Exception as e:
        import traceback
        print(f"Ошибка в /api/search-history/{history_id}/articles: {traceback.format_exc()}")
        return jsonify({'error': str(e), 'articles': []}), 500


@app.route('/api/search-history/<int:history_id>', methods=['DELETE'])
def delete_search_history(history_id):
    """Удаление истории запроса и связанных статей"""
    session = get_db_session()
    try:
        search_history = session.query(SearchHistory).filter_by(id=history_id).first()
        if not search_history:
            return jsonify({'error': 'Запись истории не найдена'}), 404
        
        # Подсчет статей перед удалением
        articles_count = session.query(NewsArticle).filter(
            NewsArticle.search_history_id == history_id
        ).count()
        
        # Удаление истории (статьи удалятся каскадно благодаря cascade)
        session.delete(search_history)
        session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Удалено: запись истории и {articles_count} связанных статей'
        })
    except Exception as e:
        session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        session.close()


@app.route('/api/statistics')
def get_statistics():
    """Получение общей статистики по результатам работы"""
    try:
        session = get_db_session()
        try:
            total = session.query(NewsArticle).count()
            relevant = session.query(NewsArticle).filter(
                NewsArticle.is_relevant == True,
                NewsArticle.is_duplicate == False
            ).count()
            duplicates_count = session.query(NewsArticle).filter(
                NewsArticle.is_duplicate == True
            ).count()
            unique_non_relevant = total - relevant - duplicates_count
            
            # Статистика по источникам
            sources_stats = session.query(
                NewsArticle.source,
                func.count(NewsArticle.id).label('count')
            ).filter(
                NewsArticle.is_duplicate == False
            ).group_by(NewsArticle.source).all()
            
            sources = [{'name': source, 'count': count} for source, count in sources_stats]
            
            # Последние поиски (по истории запросов) - группируем по search_history_id
            last_searches = session.query(
                SearchHistory.created_at,
                SearchHistory.id,
                func.count(NewsArticle.id).label('count')
            ).outerjoin(
                NewsArticle, 
                (SearchHistory.id == NewsArticle.search_history_id) & 
                (NewsArticle.is_duplicate == False)
            ).group_by(
                SearchHistory.id, 
                SearchHistory.created_at
            ).order_by(
                SearchHistory.created_at.desc()
            ).limit(10).all()
            
            searches = [{
                'date': created_at.isoformat() if created_at else None,
                'count': count or 0
            } for created_at, history_id, count in last_searches]
            
            return jsonify({
                'total': total,
                'relevant': relevant,
                'duplicates': duplicates_count,
                'unique_non_relevant': unique_non_relevant,
                'sources': sources,
                'last_searches': searches
            })
        except Exception as e:
            import traceback
            print(f"Ошибка в /api/statistics: {traceback.format_exc()}")
            return jsonify({
                'error': str(e),
                'total': 0,
                'relevant': 0,
                'duplicates': 0,
                'unique_non_relevant': 0,
                'sources': [],
                'last_searches': []
            }), 500
        finally:
            session.close()
    except Exception as e:
        import traceback
        print(f"Ошибка в /api/statistics: {traceback.format_exc()}")
        return jsonify({
            'error': str(e),
            'total': 0,
            'relevant': 0,
            'duplicates': 0,
            'unique_non_relevant': 0,
            'sources': [],
            'last_searches': []
        }), 500


@app.route('/api/semantic-search', methods=['POST'])
def semantic_search():
    """Семантический поиск статей по текстовому запросу"""
    try:
        data = request.json
        query = data.get('query', '').strip()
        search_history_id = data.get('search_history_id')
        if search_history_id is not None:
            search_history_id = int(search_history_id)
        threshold = float(data.get('threshold', 0.7))
        limit = int(data.get('limit', 20))
        
        if not query:
            return jsonify({'error': 'Не указан поисковый запрос'}), 400
        
        if not (0 <= threshold <= 1):
            return jsonify({'error': 'Порог схожести должен быть от 0.0 до 1.0'}), 400
        
        from agents.embeddings import semantic_search
        
        results = semantic_search(query, search_history_id, threshold, limit)
        
        articles_data = []
        for article_data, similarity in results:
            # article_data уже содержит все нужные данные
            article_data['similarity_score'] = round(similarity, 3)
            articles_data.append(article_data)
        
        return jsonify({
            'articles': articles_data,
            'query': query,
            'found': len(articles_data)
        })
    except Exception as e:
        import traceback
        print(f"Ошибка в /api/semantic-search: {traceback.format_exc()}")
        return jsonify({'error': str(e), 'articles': []}), 500


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Получение всех системных настроек"""
    try:
        category = request.args.get('category')
        print(f"API /api/settings вызван, category={category}")
        settings = get_all_settings(category=category)
        print(f"get_all_settings вернул {len(settings)} настроек")
        
        # Отладочная информация
        print(f"Запрос настроек: category={category}, найдено: {len(settings)}")
        if settings:
            print(f"Примеры настроек: {[s.get('key', 'N/A') for s in settings[:3]]}")
        if len(settings) == 0:
            print("Предупреждение: настройки не найдены. Проверяем, инициализированы ли они...")
            # Пытаемся инициализировать, если таблица пустая
            from models import init_default_settings
            try:
                init_default_settings()
                # Пробуем загрузить снова
                settings = get_all_settings(category=category)
                print(f"После инициализации найдено: {len(settings)}")
            except Exception as init_error:
                print(f"Ошибка при попытке инициализации: {init_error}")
        
        return jsonify({
            'success': True,
            'settings': settings,
            'count': len(settings)
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Ошибка в /api/settings: {error_trace}")
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': error_trace
        }), 500


@app.route('/api/settings/init', methods=['POST'])
def init_settings():
    """Принудительная инициализация настроек по умолчанию"""
    try:
        from models import init_default_settings, SystemSettings, get_db_session
        
        session = get_db_session()
        try:
            # Удаляем все существующие настройки
            session.query(SystemSettings).delete()
            session.commit()
            print("Существующие настройки удалены")
        except Exception as e:
            session.rollback()
            print(f"Ошибка при удалении настроек: {e}")
        finally:
            session.close()
        
        # Инициализируем заново
        init_default_settings()
        
        # Загружаем созданные настройки
        settings = get_all_settings()
        
        return jsonify({
            'success': True,
            'message': f'Инициализировано {len(settings)} настроек по умолчанию',
            'settings': settings,
            'count': len(settings)
        })
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Ошибка в /api/settings/init: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace
        }), 500


@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Обновление системных настроек"""
    try:
        data = request.json
        if not data or 'settings' not in data:
            return jsonify({'success': False, 'error': 'Не указаны настройки для обновления'}), 400
        
        updated = []
        errors = []
        
        for setting_data in data['settings']:
            key = setting_data.get('key')
            value = setting_data.get('value')
            
            if not key:
                errors.append('Не указан ключ настройки')
                continue
            
            if value is None:
                errors.append(f'Не указано значение для настройки {key}')
                continue
            
            description = setting_data.get('description')
            category = setting_data.get('category', 'general')
            
            if update_setting(key, str(value), description, category):
                updated.append(key)
            else:
                errors.append(f'Ошибка при обновлении настройки {key}')
        
        if errors:
            return jsonify({
                'success': False,
                'error': 'Ошибки при обновлении настроек',
                'errors': errors,
                'updated': updated
            }), 400
        
        return jsonify({
            'success': True,
            'message': f'Обновлено настроек: {len(updated)}',
            'updated': updated
        })
    except Exception as e:
        import traceback
        print(f"Ошибка в /api/settings POST: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/clear-db', methods=['POST'])
def clear_database():
    """Очистка базы данных"""
    session = None
    try:
        from sqlalchemy import inspect
        
        # Проверка существования таблицы
        inspector = inspect(engine)
        if 'news_articles' not in inspector.get_table_names():
            return jsonify({
                'success': True,
                'message': 'База данных уже пуста (таблица не существует)'
            })
        
        session = get_db_session()
        
        # Подсчет статей перед удалением
        count = session.query(NewsArticle).count()
        
        # Удаление всех статей
        if count > 0:
            session.query(NewsArticle).delete()
            session.commit()
        
        return jsonify({
            'success': True,
            'message': f'База данных очищена. Удалено статей: {count}'
        })
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"Ошибка при очистке БД: {error_msg}")
        traceback.print_exc()
        
        if session:
            try:
                session.rollback()
            except Exception as rollback_error:
                print(f"Ошибка при rollback: {rollback_error}")
        
        # Всегда возвращаем JSON, даже при ошибке
        try:
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
        except Exception as json_error:
            # Если даже jsonify не работает, возвращаем простой текст
            from flask import Response
            return Response(
                f'{{"success": false, "error": "{error_msg}"}}',
                mimetype='application/json',
                status=500
            )
    finally:
        if session:
            try:
                session.close()
            except Exception as close_error:
                print(f"Ошибка при закрытии сессии: {close_error}")


if __name__ == '__main__':
    app.run(
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        debug=Config.FLASK_DEBUG
    )

