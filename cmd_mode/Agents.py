"""Оркестрация собственных AI‑агентов для обработки новостей (CLI‑режим)."""

from typing import List

from agents.rss_collector import collect_rss_news
from agents.deduplicator import find_duplicates, mark_duplicates
from agents.classifier import classify_articles_with_settings
from agents.summarizer import generate_summaries_for_articles
from agents.embeddings import generate_embeddings_for_articles_by_ids
from config import Config
from models import NewsArticle, SearchHistory, get_db_session, init_db


class NewsProcessingOrchestrator:
    """Высокоуровневый оркестратор пайплайна обработки новостей."""

    def __init__(self) -> None:
        """Инициализация БД и зависимостей."""
        init_db()

    def process_news(
        self,
        feed_urls: List[str] | None = None,
        criteria: str | None = None,
        llm_model: str | None = None,
        llm_temperature: float | None = None,
        similarity_threshold: float | None = None,
        relevance_threshold: float | None = None,
    ) -> None:
        """Запускает полный цикл обработки новостей."""
        if feed_urls is None:
            feed_urls = Config.RSS_FEEDS

        if criteria is None:
            criteria = Config.SELECTION_CRITERIA

        # Использование переданных параметров или значений по умолчанию
        if llm_model is None:
            llm_model = Config.LLM_MODEL
        if llm_temperature is None:
            llm_temperature = Config.LLM_TEMPERATURE
        if similarity_threshold is None:
            similarity_threshold = Config.SIMILARITY_THRESHOLD
        if relevance_threshold is None:
            relevance_threshold = Config.RELEVANCE_THRESHOLD

        if not feed_urls:
            print("Ошибка: не указаны RSS‑каналы")
            return

        if not criteria:
            print("Ошибка: не указан критерий отбора")
            return

        print(f"Начало обработки новостей из {len(feed_urls)} каналов...")
        print(f"Критерий отбора: {criteria}")
        print(
            "Настройки: "
            f"модель={llm_model}, temperature={llm_temperature}, "
            f"порог схожести={similarity_threshold}, "
            f"порог релевантности={relevance_threshold}"
        )

        # Создание записи истории запроса
        session = get_db_session()
        search_history_id: int | None = None
        try:
            search_history = SearchHistory(
                rss_feeds="\n".join(feed_urls),
                selection_criteria=criteria,
                llm_model=llm_model,
                llm_temperature=llm_temperature,
                similarity_threshold=similarity_threshold,
                openai_api_base=Config.OPENAI_API_BASE or "",
                results_data={
                    "relevance_threshold": relevance_threshold,
                },
            )
            session.add(search_history)
            session.commit()
            search_history_id = search_history.id
            print(f"Создана запись истории запроса: ID {search_history_id}")
        except Exception as e:  # noqa: BLE001
            session.rollback()
            print(f"Ошибка при создании истории запроса: {e}")
        finally:
            session.close()

        # Шаг 1: Сбор новостей
        print("\n=== Шаг 1: Сбор новостей из RSS‑каналов ===")
        articles = collect_rss_news(feed_urls)

        if articles:
            print(f"Собрано {len(articles)} новых статей")

            # Сохранение статей в БД
            session = get_db_session()
            try:
                saved_count = 0
                for article in articles:
                    # Проверяем, не существует ли уже эта статья в текущем запросе
                    if search_history_id:
                        existing = (
                            session.query(NewsArticle)
                            .filter(
                                NewsArticle.link == article.link,
                                NewsArticle.search_history_id == search_history_id,
                            )
                            .first()
                        )

                        if existing:
                            continue  # Пропускаем, если уже есть в этом запросе

                        article.search_history_id = search_history_id

                    session.add(article)
                    saved_count += 1

                session.commit()
                print(
                    f"Сохранено {saved_count} новых статей "
                    f"(из {len(articles)} собранных)"
                )
            except Exception as e:  # noqa: BLE001
                session.rollback()
                print(f"Ошибка при сохранении статей: {e}")
            finally:
                session.close()
        else:
            print("Новых новостей не найдено")

        # Получение необработанных статей для текущего запроса
        session = get_db_session()
        try:
            if search_history_id:
                unprocessed_articles = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.search_history_id == search_history_id,
                        NewsArticle.is_duplicate.is_(False),
                        NewsArticle.relevance_score.is_(None),
                    )
                    .all()
                )
            else:
                # Fallback для старых записей без search_history_id
                unprocessed_articles = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.is_duplicate.is_(False),
                        NewsArticle.relevance_score.is_(None),
                    )
                    .all()
                )
        finally:
            session.close()

        if not unprocessed_articles:
            print("Нет статей для обработки")
            return

        # Шаг 2: Дедупликация
        print(f"\n=== Шаг 2: Дедупликация {len(unprocessed_articles)} статей ===")
        duplicates = find_duplicates(
            unprocessed_articles, similarity_threshold, search_history_id
        )

        if duplicates:
            mark_duplicates(unprocessed_articles, duplicates)
            print(f"Найдено {len(duplicates)} дубликатов")
        else:
            print("Дубликаты не найдены")

        # Получение уникальных статей для классификации
        session = get_db_session()
        try:
            if search_history_id:
                unique_articles = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.search_history_id == search_history_id,
                        NewsArticle.is_duplicate.is_(False),
                        NewsArticle.relevance_score.is_(None),
                    )
                    .all()
                )
            else:
                unique_articles = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.is_duplicate.is_(False),
                        NewsArticle.relevance_score.is_(None),
                    )
                    .all()
                )
            # Получаем ID статей до закрытия сессии
            unique_article_ids = [article.id for article in unique_articles]
        finally:
            session.close()

        # Шаг 3: Классификация
        print(f"\n=== Шаг 3: Классификация {len(unique_articles)} уникальных статей ===")
        classify_articles_with_settings(
            unique_articles, criteria, llm_model, llm_temperature, relevance_threshold
        )
        print(f"Классифицировано {len(unique_articles)} статей")

        # Шаг 4: Генерация саммари для релевантных статей
        session = get_db_session()
        try:
            if search_history_id:
                relevant_articles = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.search_history_id == search_history_id,
                        NewsArticle.is_duplicate.is_(False),
                        NewsArticle.is_relevant.is_(True),
                    )
                    .all()
                )
            else:
                relevant_articles = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.is_duplicate.is_(False),
                        NewsArticle.is_relevant.is_(True),
                    )
                    .all()
                )
        finally:
            session.close()

        if relevant_articles:
            try:
                print(
                    "\n=== Шаг 4: Генерация саммари для "
                    f"{len(relevant_articles)} релевантных статей ==="
                )
                generate_summaries_for_articles(
                    relevant_articles, llm_model, llm_temperature
                )
                print(f"Саммари сгенерировано для {len(relevant_articles)} статей")
            except Exception as e:  # noqa: BLE001
                print(f"Ошибка при генерации саммари: {e}")
                import traceback

                traceback.print_exc()
        else:
            print("\n=== Шаг 4: Нет релевантных статей для генерации саммари ===")

        # Шаг 5: Генерация embeddings для всех уникальных статей
        try:
            print(
                "\n=== Шаг 5: Генерация векторных представлений "
                f"для {len(unique_article_ids)} статей ==="
            )
            generate_embeddings_for_articles_by_ids(unique_article_ids, search_history_id)
            print(f"Векторные представления сгенерированы для {len(unique_articles)} статей")
        except Exception as e:  # noqa: BLE001
            print(f"Ошибка при генерации embeddings: {e}")
            import traceback

            traceback.print_exc()

        # Итоговая статистика
        session = get_db_session()
        try:
            if search_history_id:
                total = (
                    session.query(NewsArticle)
                    .filter(NewsArticle.search_history_id == search_history_id)
                    .count()
                )
                relevant = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.search_history_id == search_history_id,
                        NewsArticle.is_relevant.is_(True),
                        NewsArticle.is_duplicate.is_(False),
                    )
                    .count()
                )
                duplicates_count = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.search_history_id == search_history_id,
                        NewsArticle.is_duplicate.is_(True),
                    )
                    .count()
                )
            else:
                total = session.query(NewsArticle).count()
                relevant = (
                    session.query(NewsArticle)
                    .filter(
                        NewsArticle.is_relevant.is_(True),
                        NewsArticle.is_duplicate.is_(False),
                    )
                    .count()
                )
                duplicates_count = (
                    session.query(NewsArticle)
                    .filter(NewsArticle.is_duplicate.is_(True))
                    .count()
                )

            unique_non_relevant = total - relevant - duplicates_count

            # Обновление истории запроса с результатами
            if search_history_id:
                search_history = (
                    session.query(SearchHistory)
                    .filter_by(id=search_history_id)
                    .first()
                )
                if search_history:
                    search_history.results_data = {
                        "total": total,
                        "relevant": relevant,
                        "duplicates": duplicates_count,
                        "unique_non_relevant": unique_non_relevant,
                        "collected_articles": len(articles) if articles else 0,
                        "processed_articles": len(unique_articles),
                    }
                    session.commit()
        finally:
            session.close()

        print("\n=== Итоговая статистика ===")
        print(f"Всего статей: {total}")
        print(f"Релевантных: {relevant}")
        print(f"Дубликатов: {duplicates_count}")
        print(f"Уникальных нерелевантных: {unique_non_relevant}")


def run_agents() -> None:
    """Упрощённый запуск пайплайна обработки новостей."""
    orchestrator = NewsProcessingOrchestrator()
    orchestrator.process_news()

