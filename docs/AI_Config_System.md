# Система динамической конфигурации AI провайдеров

Документация по реализации безопасной и гибкой системы переключения между различными AI провайдерами без перезапуска приложения.

---

## Содержание

1. [Обзор системы](#обзор-системы)
2. [Структура конфигурационного файла](#структура-конфигурационного-файла)
3. [Безопасная работа с API ключами](#безопасная-работа-с-api-ключами)
4. [Менеджер конфигурации](#менеджер-конфигурации)
5. [Примеры использования](#примеры-использования)
6. [Дополнительные возможности](#дополнительные-возможности)

---

## Обзор системы

Система предназначена для динамического переключения между различными AI провайдерами (OpenAI, Anthropic, Ollama и др.) без необходимости перезапуска приложения.

### Ключевые особенности

- API ключи хранятся **только** в `.env` файле (не в конфигурации)
- Проверка наличия ключа при выборе провайдера
- Ключи подставляются через функцию при вызове API (не хранятся в памяти)
- Глобальные параметры `temperature` и `max_tokens`
- Поддержка профилей (development, production)
- Множественные модели для каждого провайдера

---

## Структура конфигурационного файла

Файл `ai-configs.json` содержит информацию о провайдерах, моделях и профилях. **API ключи НЕ хранятся в этом файле.**

### ai-configs.json

```json
{
  "providers": {
    "openai": {
      "name": "OpenAI",
      "env_key": "OPENAI_API_KEY",
      "base_url": "https://api.openai.com/v1",
      "models": {
        "llm": [
          {
            "id": "gpt-4o",
            "name": "GPT-4 Optimized"
          },
          {
            "id": "gpt-4o-mini",
            "name": "GPT-4 Mini"
          },
          {
            "id": "gpt-3.5-turbo",
            "name": "GPT-3.5 Turbo"
          }
        ],
        "embedding": [
          {
            "id": "text-embedding-3-small",
            "name": "Embedding Small",
            "dimensions": 1536
          },
          {
            "id": "text-embedding-3-large",
            "name": "Embedding Large",
            "dimensions": 3072
          }
        ]
      },
      "enabled": true,
      "priority": 1
    },
    "anthropic": {
      "name": "Anthropic Claude",
      "env_key": "ANTHROPIC_API_KEY",
      "base_url": "https://api.anthropic.com",
      "models": {
        "llm": [
          {
            "id": "claude-sonnet-4-20250514",
            "name": "Claude Sonnet 4"
          },
          {
            "id": "claude-opus-4-20250514",
            "name": "Claude Opus 4"
          },
          {
            "id": "claude-haiku-4-20250514",
            "name": "Claude Haiku 4"
          }
        ],
        "embedding": []
      },
      "enabled": true,
      "priority": 2
    },
    "ollama": {
      "name": "Ollama (Local)",
      "env_key": "OLLAMA_API_KEY",
      "base_url": "http://localhost:11434",
      "models": {
        "llm": [
          {
            "id": "llama3.2",
            "name": "Llama 3.2"
          },
          {
            "id": "mistral",
            "name": "Mistral"
          },
          {
            "id": "qwen2.5",
            "name": "Qwen 2.5"
          }
        ],
        "embedding": [
          {
            "id": "snowflake-arctic-embed2",
            "name": "Arctic Embed 2",
            "dimensions": 768
          },
          {
            "id": "granite-embedding",
            "name": "Granite Embedding",
            "dimensions": 1024
          }
        ]
      },
      "enabled": true,
      "priority": 3
    },
    "proxyapi": {
      "name": "ProxyAPI (OpenAI Compatible)",
      "env_key": "PROXYAPI_API_KEY",
      "base_url": "https://openai.api.proxyapi.ru/v1",
      "models": {
        "llm": [
          {
            "id": "gpt-4o-mini",
            "name": "GPT-4 Mini (Proxy)"
          },
          {
            "id": "gpt-4o",
            "name": "GPT-4 (Proxy)"
          }
        ],
        "embedding": [
          {
            "id": "text-embedding-3-small",
            "name": "Embedding Small (Proxy)",
            "dimensions": 1536
          }
        ]
      },
      "enabled": true,
      "priority": 4
    }
  },
  "settings": {
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "profiles": {
    "development": {
      "default_provider": "ollama",
      "default_llm": "llama3.2",
      "default_embedding": "snowflake-arctic-embed2"
    },
    "production": {
      "default_provider": "openai",
      "default_llm": "gpt-4o-mini",
      "default_embedding": "text-embedding-3-small"
    },
    "experimental": {
      "default_provider": "anthropic",
      "default_llm": "claude-sonnet-4-20250514",
      "default_embedding": null
    }
  },
  "current_profile": "development"
}
```

### Описание полей

#### Провайдер (provider)

- `name` - Человекочитаемое название провайдера
- `env_key` - Имя переменной окружения для API ключа
- `base_url` - Базовый URL API
- `models` - Словарь с типами моделей (llm, embedding)
- `enabled` - Флаг активности провайдера
- `priority` - Приоритет провайдера (используется для сортировки)

#### Модель (model)

- `id` - Идентификатор модели для API
- `name` - Человекочитаемое название модели
- `dimensions` - (только для embedding) Размерность векторов

#### Глобальные настройки (settings)

- `temperature` - Температура генерации (0.0 - 2.0)
- `max_tokens` - Максимальное количество токенов в ответе

#### Профиль (profile)

- `default_provider` - ID провайдера по умолчанию
- `default_llm` - ID LLM модели по умолчанию
- `default_embedding` - ID embedding модели по умолчанию (может быть null)

---

## Безопасная работа с API ключами

Все секретные ключи хранятся **только** в файле `.env` и не попадают в конфигурацию или память приложения.

### Файл .env

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Ollama (может быть любым значением, так как Ollama не требует ключ)
OLLAMA_API_KEY=ollama

# ProxyAPI
PROXYAPI_API_KEY=your_proxy_key

# Другие провайдеры...
```

### Принципы безопасности

1. **API ключи никогда не сохраняются в переменных класса** - хранятся только ID провайдера и имя переменной окружения
2. **Проверка наличия ключа в `.env` перед выбором провайдера** - метод `is_provider_available()`
3. **Ключи читаются через функцию только при вызове API** - метод `get_api_key()`
4. **Файл `.env` добавлен в `.gitignore`** - предотвращает случайную публикацию ключей

### Пример .gitignore

```gitignore
# Environment variables
.env
.env.local
.env.*.local

# AI configuration with sensitive data (if you accidentally put keys there)
ai-configs.local.json
```

---

## Менеджер конфигурации

Класс `AIConfigManager` управляет конфигурацией и обеспечивает безопасный доступ к API ключам.

### ai_config_manager.py

```python
import json
import os
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv


class AIConfigManager:
    """
    Менеджер конфигурации AI провайдеров с безопасным управлением API ключами.
    
    Основные принципы:
    - API ключи хранятся только в .env файле
    - Ключи не кэшируются в памяти
    - Проверка доступности ключа при выборе провайдера
    - Глобальные параметры temperature и max_tokens
    """
    
    def __init__(self, config_path: str = "ai-configs.json"):
        """
        Инициализация менеджера конфигурации.
        
        Args:
            config_path: Путь к файлу конфигурации JSON
        """
        load_dotenv()  # Загружаем переменные окружения из .env
        self.config_path = config_path
        self.config = self._load_config()
        
        # Храним только ID, не сами данные
        self._current_provider = None
        self._current_llm = None
        self._current_embedding = None
    
    def _load_config(self) -> Dict:
        """Загружает конфигурацию из JSON файла."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def reload_config(self):
        """
        Перезагружает конфигурацию из файла.
        Полезно для горячей перезагрузки настроек.
        """
        self.config = self._load_config()
        load_dotenv(override=True)  # Перезагружаем .env
    
    def save_config(self):
        """Сохраняет текущую конфигурацию в файл."""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def get_providers(self, enabled_only: bool = True) -> Dict:
        """
        Возвращает список провайдеров.
        
        Args:
            enabled_only: Возвращать только включенные провайдеры
            
        Returns:
            Словарь провайдеров
        """
        providers = self.config['providers']
        if enabled_only:
            return {k: v for k, v in providers.items() if v.get('enabled', True)}
        return providers
    
    def get_provider_config(self, provider_id: str) -> Optional[Dict]:
        """
        Получает конфигурацию конкретного провайдера.
        
        Args:
            provider_id: Идентификатор провайдера
            
        Returns:
            Конфигурация провайдера или None
        """
        return self.config['providers'].get(provider_id)
    
    def is_provider_available(self, provider_id: str) -> bool:
        """
        Проверяет доступность провайдера (наличие API ключа в .env).
        
        Args:
            provider_id: Идентификатор провайдера
            
        Returns:
            True если провайдер доступен (есть ключ в .env)
        """
        provider = self.get_provider_config(provider_id)
        if not provider:
            return False
        
        if not provider.get('enabled', True):
            return False
        
        # Проверяем наличие ключа в переменных окружения
        env_key = provider.get('env_key')
        if not env_key:
            return False
        
        api_key = os.getenv(env_key)
        return api_key is not None and api_key.strip() != ""
    
    def get_available_providers(self) -> Dict[str, Dict]:
        """
        Возвращает список провайдеров с информацией о доступности.
        
        Returns:
            Словарь вида {provider_id: {name, has_key, models, ...}}
        """
        result = {}
        for provider_id, provider_config in self.get_providers().items():
            result[provider_id] = {
                'name': provider_config['name'],
                'has_key': self.is_provider_available(provider_id),
                'base_url': provider_config['base_url'],
                'models': provider_config['models'],
                'priority': provider_config.get('priority', 999)
            }
        return result
    
    def get_models(self, provider_id: str, model_type: str = 'llm') -> List[Dict]:
        """
        Получает список моделей для провайдера.
        
        Args:
            provider_id: Идентификатор провайдера
            model_type: Тип модели ('llm' или 'embedding')
            
        Returns:
            Список моделей
        """
        provider = self.get_provider_config(provider_id)
        if not provider:
            return []
        return provider.get('models', {}).get(model_type, [])
    
    def get_model_config(self, provider_id: str, model_id: str, 
                        model_type: str = 'llm') -> Optional[Dict]:
        """
        Получает конфигурацию конкретной модели.
        
        Args:
            provider_id: Идентификатор провайдера
            model_id: Идентификатор модели
            model_type: Тип модели ('llm' или 'embedding')
            
        Returns:
            Конфигурация модели или None
        """
        models = self.get_models(provider_id, model_type)
        for model in models:
            if model['id'] == model_id:
                return model
        return None
    
    def set_active_provider(self, provider_id: str, 
                          llm_model_id: Optional[str] = None,
                          embedding_model_id: Optional[str] = None):
        """
        Устанавливает активного провайдера и модели.
        Проверяет наличие API ключа в .env перед установкой.
        
        Args:
            provider_id: Идентификатор провайдера
            llm_model_id: Идентификатор LLM модели (опционально)
            embedding_model_id: Идентификатор embedding модели (опционально)
            
        Raises:
            ValueError: Если провайдер не найден, отключен или нет API ключа
        """
        provider = self.get_provider_config(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found")
        
        if not provider.get('enabled', True):
            raise ValueError(f"Provider '{provider_id}' is disabled")
        
        # КРИТИЧНО: Проверка наличия API ключа
        if not self.is_provider_available(provider_id):
            env_key = provider.get('env_key', 'UNKNOWN')
            raise ValueError(
                f"Provider '{provider_id}' is not available. "
                f"API key '{env_key}' not found in .env file"
            )
        
        self._current_provider = provider_id
        
        # Устанавливаем LLM модель
        if llm_model_id:
            if not self.get_model_config(provider_id, llm_model_id, 'llm'):
                raise ValueError(
                    f"LLM model '{llm_model_id}' not found for provider '{provider_id}'"
                )
            self._current_llm = llm_model_id
        else:
            # Берем первую доступную модель
            llm_models = self.get_models(provider_id, 'llm')
            self._current_llm = llm_models[0]['id'] if llm_models else None
        
        # Устанавливаем Embedding модель
        if embedding_model_id:
            if not self.get_model_config(provider_id, embedding_model_id, 'embedding'):
                raise ValueError(
                    f"Embedding model '{embedding_model_id}' not found "
                    f"for provider '{provider_id}'"
                )
            self._current_embedding = embedding_model_id
        else:
            embedding_models = self.get_models(provider_id, 'embedding')
            self._current_embedding = embedding_models[0]['id'] if embedding_models else None
    
    def get_api_key(self) -> str:
        """
        Получает API ключ для текущего провайдера из .env.
        КРИТИЧНО: Ключ читается из переменных окружения каждый раз,
        не сохраняется в памяти.
        
        Returns:
            API ключ
            
        Raises:
            ValueError: Если провайдер не выбран или ключ не найден
        """
        if not self._current_provider:
            raise ValueError("No provider selected. Call set_active_provider() first")
        
        provider = self.get_provider_config(self._current_provider)
        env_key = provider.get('env_key')
        
        if not env_key:
            raise ValueError(f"No env_key specified for provider '{self._current_provider}'")
        
        api_key = os.getenv(env_key)
        
        if not api_key or api_key.strip() == "":
            raise ValueError(
                f"API key '{env_key}' not found in environment variables. "
                f"Please add it to your .env file"
            )
        
        return api_key.strip()
    
    def get_active_config(self) -> Dict[str, Any]:
        """
        Возвращает текущую активную конфигурацию.
        НЕ включает API ключ - используйте get_api_key() при вызове API.
        
        Returns:
            Словарь с конфигурацией (без API ключа)
        """
        if not self._current_provider:
            # Загружаем из профиля по умолчанию
            self.load_profile()
        
        provider = self.get_provider_config(self._current_provider)
        llm_config = self.get_model_config(
            self._current_provider, self._current_llm, 'llm'
        )
        embedding_config = self.get_model_config(
            self._current_provider, self._current_embedding, 'embedding'
        ) if self._current_embedding else None
        
        # Получаем глобальные настройки
        settings = self.config.get('settings', {})
        
        return {
            'provider_id': self._current_provider,
            'provider_name': provider['name'],
            'base_url': provider['base_url'],
            'env_key': provider['env_key'],  # Имя переменной, НЕ значение
            'llm': llm_config,
            'embedding': embedding_config,
            'temperature': settings.get('temperature', 0.7),
            'max_tokens': settings.get('max_tokens', 4096)
        }
    
    def load_profile(self, profile_name: Optional[str] = None):
        """
        Загружает профиль конфигурации.
        
        Args:
            profile_name: Имя профиля или None для текущего
            
        Returns:
            Конфигурация профиля
            
        Raises:
            ValueError: Если профиль не найден
        """
        if not profile_name:
            profile_name = self.config.get('current_profile', 'development')
        
        profile = self.config['profiles'].get(profile_name)
        if not profile:
            raise ValueError(f"Profile '{profile_name}' not found")
        
        self.set_active_provider(
            profile['default_provider'],
            profile.get('default_llm'),
            profile.get('default_embedding')
        )
        
        return profile
    
    def update_settings(self, temperature: Optional[float] = None,
                       max_tokens: Optional[int] = None):
        """
        Обновляет глобальные параметры генерации.
        
        Args:
            temperature: Температура (0.0 - 2.0)
            max_tokens: Максимальное количество токенов
        """
        settings = self.config.get('settings', {})
        
        if temperature is not None:
            if not 0.0 <= temperature <= 2.0:
                raise ValueError("Temperature must be between 0.0 and 2.0")
            settings['temperature'] = temperature
        
        if max_tokens is not None:
            if max_tokens < 1:
                raise ValueError("max_tokens must be positive")
            settings['max_tokens'] = max_tokens
        
        self.config['settings'] = settings
        self.save_config()
    
    def get_settings(self) -> Dict[str, Any]:
        """
        Получает текущие глобальные настройки.
        
        Returns:
            Словарь настроек {temperature, max_tokens}
        """
        return self.config.get('settings', {
            'temperature': 0.7,
            'max_tokens': 4096
        })
    
    def add_provider(self, provider_id: str, provider_config: Dict):
        """
        Добавляет нового провайдера в конфигурацию.
        
        Args:
            provider_id: Уникальный идентификатор провайдера
            provider_config: Конфигурация провайдера
        """
        if provider_id in self.config['providers']:
            raise ValueError(f"Provider '{provider_id}' already exists")
        
        # Проверяем обязательные поля
        required_fields = ['name', 'env_key', 'base_url', 'models']
        for field in required_fields:
            if field not in provider_config:
                raise ValueError(f"Missing required field: {field}")
        
        self.config['providers'][provider_id] = provider_config
        self.save_config()
    
    def update_provider(self, provider_id: str, updates: Dict):
        """
        Обновляет конфигурацию существующего провайдера.
        
        Args:
            provider_id: Идентификатор провайдера
            updates: Словарь с обновлениями
        """
        if provider_id not in self.config['providers']:
            raise ValueError(f"Provider '{provider_id}' not found")
        
        self.config['providers'][provider_id].update(updates)
        self.save_config()
    
    def set_current_profile(self, profile_name: str):
        """
        Устанавливает текущий профиль и загружает его.
        
        Args:
            profile_name: Имя профиля
        """
        if profile_name not in self.config['profiles']:
            raise ValueError(f"Profile '{profile_name}' not found")
        
        self.config['current_profile'] = profile_name
        self.save_config()
        self.load_profile(profile_name)
```

---

## Примеры использования

### Базовая инициализация

```python
from ai_config_manager import AIConfigManager

# Инициализация менеджера
config_manager = AIConfigManager()

# Загрузка профиля разработки
config_manager.load_profile('development')

# Проверка, какой провайдер активен
config = config_manager.get_active_config()
print(f"Активный провайдер: {config['provider_name']}")
print(f"LLM модель: {config['llm']['name']}")
print(f"Temperature: {config['temperature']}")
print(f"Max tokens: {config['max_tokens']}")
```

### Получение конфигурации для API вызова

```python
# Получение активной конфигурации (без API ключа)
config = config_manager.get_active_config()

# КРИТИЧНО: API ключ получаем только при вызове API
api_key = config_manager.get_api_key()

# Пример использования с OpenAI
import openai

response = openai.ChatCompletion.create(
    api_key=api_key,  # Получен из .env через функцию
    base_url=config['base_url'],
    model=config['llm']['id'],
    temperature=config['temperature'],
    max_tokens=config['max_tokens'],
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

# Ключ не хранится в памяти, будет удален после выхода из scope
```

### Динамическое переключение провайдера

```python
# Переключение на OpenAI
try:
    config_manager.set_active_provider(
        'openai',
        llm_model_id='gpt-4o-mini',
        embedding_model_id='text-embedding-3-small'
    )
    print("✓ Успешно переключено на OpenAI")
    
except ValueError as e:
    print(f"✗ Ошибка переключения: {e}")
    # Возможные причины:
    # - Провайдер не найден
    # - Провайдер отключен
    # - Отсутствует API ключ в .env

# Переключение на Anthropic
try:
    config_manager.set_active_provider(
        'anthropic',
        llm_model_id='claude-sonnet-4-20250514'
    )
    print("✓ Успешно переключено на Anthropic")
    
except ValueError as e:
    print(f"✗ Ошибка: {e}")

# Переключение на локальную Ollama
try:
    config_manager.set_active_provider(
        'ollama',
        llm_model_id='llama3.2',
        embedding_model_id='snowflake-arctic-embed2'
    )
    print("✓ Успешно переключено на Ollama")
    
except ValueError as e:
    print(f"✗ Ошибка: {e}")
```

### Проверка доступных провайдеров

```python
# Получение информации о доступности провайдеров
available = config_manager.get_available_providers()

print("Доступные AI провайдеры:\n")
for provider_id, info in available.items():
    status = "✓ Доступен" if info['has_key'] else "✗ Нет API ключа"
    print(f"{info['name']}: {status}")
    
    if info['has_key']:
        print(f"  LLM модели:")
        for model in info['models']['llm']:
            print(f"    - {model['name']} ({model['id']})")
        
        if info['models']['embedding']:
            print(f"  Embedding модели:")
            for model in info['models']['embedding']:
                dims = model.get('dimensions', 'unknown')
                print(f"    - {model['name']} ({model['id']}) - {dims}D")
    print()

# Пример вывода:
# OpenAI: ✓ Доступен
#   LLM модели:
#     - GPT-4 Optimized (gpt-4o)
#     - GPT-4 Mini (gpt-4o-mini)
#   Embedding модели:
#     - Embedding Small (text-embedding-3-small) - 1536D
#
# Anthropic Claude: ✗ Нет API ключа
#
# Ollama (Local): ✓ Доступен
#   LLM модели:
#     - Llama 3.2 (llama3.2)
```

### Работа с конкретным провайдером

```python
# Проверка доступности конкретного провайдера
if config_manager.is_provider_available('openai'):
    print("OpenAI доступен")
    config_manager.set_active_provider('openai', 'gpt-4o-mini')
else:
    print("OpenAI недоступен. Проверьте наличие OPENAI_API_KEY в .env")

# Получение списка моделей провайдера
llm_models = config_manager.get_models('openai', 'llm')
print("\nДоступные LLM модели OpenAI:")
for model in llm_models:
    print(f"  - {model['name']} ({model['id']})")

embedding_models = config_manager.get_models('openai', 'embedding')
print("\nДоступные Embedding модели OpenAI:")
for model in embedding_models:
    print(f"  - {model['name']} ({model['id']}) - {model['dimensions']}D")
```

### Изменение глобальных параметров

```python
# Обновление temperature и max_tokens
config_manager.update_settings(
    temperature=0.9,
    max_tokens=8192
)

# Получение текущих настроек
settings = config_manager.get_settings()
print(f"Температура: {settings['temperature']}")
print(f"Макс. токенов: {settings['max_tokens']}")

# Эти настройки будут применяться ко всем провайдерам
config = config_manager.get_active_config()
print(f"Активная конфигурация использует: T={config['temperature']}, "
      f"max_tokens={config['max_tokens']}")
```

### Работа с профилями

```python
# Переключение между профилями
config_manager.load_profile('production')
print("Загружен production профиль")

config_manager.load_profile('development')
print("Загружен development профиль")

# Установка профиля по умолчанию
config_manager.set_current_profile('production')
print("Production установлен как профиль по умолчанию")

# При следующем запуске будет загружен production профиль
```

### Горячая перезагрузка конфигурации

```python
# Изменили ai-configs.json вручную, перезагружаем без перезапуска приложения
config_manager.reload_config()
print("Конфигурация перезагружена")

# Также перезагружаются переменные из .env
# Полезно если добавили новый API ключ
```

### Комплексный пример: создание универсальной функции вызова

```python
def call_llm_api(prompt: str, **kwargs) -> str:
    """
    Универсальная функция для вызова LLM API.
    Автоматически использует текущего провайдера.
    """
    config = config_manager.get_active_config()
    api_key = config_manager.get_api_key()
    
    # Параметры по умолчанию из конфигурации
    temperature = kwargs.get('temperature', config['temperature'])
    max_tokens = kwargs.get('max_tokens', config['max_tokens'])
    
    # Определяем провайдера и вызываем соответствующий API
    if config['provider_id'] == 'openai':
        response = openai.ChatCompletion.create(
            api_key=api_key,
            base_url=config['base_url'],
            model=config['llm']['id'],
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    
    elif config['provider_id'] == 'anthropic':
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=config['llm']['id'],
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    
    elif config['provider_id'] == 'ollama':
        import requests
        response = requests.post(
            f"{config['base_url']}/api/generate",
            json={
                "model": config['llm']['id'],
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
        )
        return response.json()['response']
    
    else:
        raise ValueError(f"Unsupported provider: {config['provider_id']}")


# Использование
result = call_llm_api("Объясни квантовую механику простыми словами")
print(result)

# Переключаем провайдера и повторяем запрос
config_manager.set_active_provider('anthropic', 'claude-sonnet-4-20250514')
result = call_llm_api("Объясни квантовую механику простыми словами")
print(result)
```

---

## Дополнительные возможности

### Добавление нового провайдера

```python
# Добавление нового провайдера
new_provider = {
    "name": "Google Gemini",
    "env_key": "GOOGLE_API_KEY",
    "base_url": "https://generativelanguage.googleapis.com/v1",
    "models": {
        "llm": [
            {
                "id": "gemini-pro",
                "name": "Gemini Pro"
            },
            {
                "id": "gemini-pro-vision",
                "name": "Gemini Pro Vision"
            }
        ],
        "embedding": [
            {
                "id": "embedding-001",
                "name": "Embedding 001",
                "dimensions": 768
            }
        ]
    },
    "enabled": True,
    "priority": 5
}

config_manager.add_provider('google', new_provider)
print("Google Gemini добавлен в конфигурацию")

# Не забудьте добавить ключ в .env:
# GOOGLE_API_KEY=your_google_api_key
```

### Обновление конфигурации провайдера

```python
# Обновление базового URL
config_manager.update_provider('openai', {
    'base_url': 'https://api.openai.com/v2'  # Новая версия API
})

# Добавление новой модели
openai_config = config_manager.get_provider_config('openai')
openai_config['models']['llm'].append({
    'id': 'gpt-5',
    'name': 'GPT-5'
})
config_manager.update_provider('openai', openai_config)
```

### Создание пользовательского профиля

```python
# Добавление нового профиля в конфигурацию
config_manager.config['profiles']['testing'] = {
    "default_provider": "ollama",
    "default_llm": "llama3.2",
    "default_embedding": "snowflake-arctic-embed2"
}

config_manager.save_config()

# Переключение на новый профиль
config_manager.load_profile('testing')
```

### Валидация конфигурации

```python
def validate_configuration(config_manager: AIConfigManager) -> Dict[str, Any]:
    """
    Проверяет корректность конфигурации и доступность провайдеров.
    
    Returns:
        Словарь с результатами валидации
    """
    results = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'providers': {}
    }
    
    # Проверка провайдеров
    for provider_id in config_manager.get_providers().keys():
        provider_results = {
            'has_key': False,
            'has_llm_models': False,
            'has_embedding_models': False,
            'errors': []
        }
        
        # Проверка API ключа
        provider_results['has_key'] = config_manager.is_provider_available(provider_id)
        if not provider_results['has_key']:
            provider_config = config_manager.get_provider_config(provider_id)
            env_key = provider_config.get('env_key', 'UNKNOWN')
            results['warnings'].append(
                f"Provider '{provider_id}': API key '{env_key}' not found in .env"
            )
        
        # Проверка наличия моделей
        llm_models = config_manager.get_models(provider_id, 'llm')
        provider_results['has_llm_models'] = len(llm_models) > 0
        if not provider_results['has_llm_models']:
            provider_results['errors'].append("No LLM models configured")
            results['valid'] = False
        
        embedding_models = config_manager.get_models(provider_id, 'embedding')
        provider_results['has_embedding_models'] = len(embedding_models) > 0
        
        results['providers'][provider_id] = provider_results
    
    # Проверка профилей
    for profile_name, profile_config in config_manager.config['profiles'].items():
        # Проверка что default_provider существует
        default_provider = profile_config.get('default_provider')
        if default_provider not in config_manager.config['providers']:
            results['errors'].append(
                f"Profile '{profile_name}': default_provider '{default_provider}' not found"
            )
            results['valid'] = False
    
    # Проверка глобальных настроек
    settings = config_manager.get_settings()
    temp = settings.get('temperature', 0.7)
    if not 0.0 <= temp <= 2.0:
        results['errors'].append(f"Invalid temperature value: {temp} (must be 0.0-2.0)")
        results['valid'] = False
    
    max_tokens = settings.get('max_tokens', 4096)
    if max_tokens < 1:
        results['errors'].append(f"Invalid max_tokens value: {max_tokens} (must be positive)")
        results['valid'] = False
    
    return results


# Использование
validation = validate_configuration(config_manager)

if validation['valid']:
    print("✓ Конфигурация валидна")
else:
    print("✗ Обнаружены ошибки в конфигурации:")
    for error in validation['errors']:
        print(f"  - {error}")

if validation['warnings']:
    print("\n⚠ Предупреждения:")
    for warning in validation['warnings']:
        print(f"  - {warning}")

print("\nСтатус провайдеров:")
for provider_id, status in validation['providers'].items():
    key_status = "✓" if status['has_key'] else "✗"
    print(f"  {provider_id}: {key_status} API key, "
          f"{len(config_manager.get_models(provider_id, 'llm'))} LLM models")
```

### Логирование использования провайдеров

```python
import logging
from datetime import datetime
from functools import wraps

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_api_call(func):
    """Декоратор для логирования API вызовов."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        config = config_manager.get_active_config()
        
        logger.info(
            f"API Call: provider={config['provider_id']}, "
            f"model={config['llm']['id']}, "
            f"temperature={config['temperature']}, "
            f"max_tokens={config['max_tokens']}"
        )
        
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"API Call successful: duration={duration:.2f}s")
            return result
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(
                f"API Call failed: duration={duration:.2f}s, error={str(e)}"
            )
            raise
    
    return wrapper

@log_api_call
def call_llm_with_logging(prompt: str) -> str:
    return call_llm_api(prompt)

# Использование
result = call_llm_with_logging("Hello, AI!")
```

### Пример интеграции с веб-приложением (Flask)

```python
from flask import Flask, request, jsonify
from ai_config_manager import AIConfigManager

app = Flask(__name__)
config_manager = AIConfigManager()
config_manager.load_profile('production')

@app.route('/api/providers', methods=['GET'])
def get_providers():
    """Получить список доступных провайдеров."""
    providers = config_manager.get_available_providers()
    return jsonify(providers)

@app.route('/api/provider/current', methods=['GET'])
def get_current_provider():
    """Получить текущего провайдера."""
    config = config_manager.get_active_config()
    # НЕ возвращаем API ключ!
    return jsonify({
        'provider_id': config['provider_id'],
        'provider_name': config['provider_name'],
        'llm_model': config['llm'],
        'embedding_model': config['embedding'],
        'settings': {
            'temperature': config['temperature'],
            'max_tokens': config['max_tokens']
        }
    })

@app.route('/api/provider/switch', methods=['POST'])
def switch_provider():
    """Переключить провайдера."""
    data = request.json
    provider_id = data.get('provider_id')
    llm_model_id = data.get('llm_model_id')
    embedding_model_id = data.get('embedding_model_id')
    
    try:
        config_manager.set_active_provider(
            provider_id, 
            llm_model_id, 
            embedding_model_id
        )
        return jsonify({
            'success': True,
            'message': f'Switched to {provider_id}'
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/generate', methods=['POST'])
def generate():
    """Генерация текста с использованием текущего провайдера."""
    data = request.json
    prompt = data.get('prompt')
    
    if not prompt:
        return jsonify({'error': 'prompt is required'}), 400
    
    try:
        # Используем текущего провайдера
        result = call_llm_api(prompt)
        
        config = config_manager.get_active_config()
        return jsonify({
            'result': result,
            'provider': config['provider_name'],
            'model': config['llm']['id']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """Обновить глобальные настройки."""
    data = request.json
    
    try:
        config_manager.update_settings(
            temperature=data.get('temperature'),
            max_tokens=data.get('max_tokens')
        )
        return jsonify({
            'success': True,
            'settings': config_manager.get_settings()
        })
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

if __name__ == '__main__':
    app.run(debug=True)
```

---

## Заключение

Данная система обеспечивает:

- **Безопасность**: API ключи хранятся только в `.env` файле и не попадают в память приложения
- **Гибкость**: Динамическое переключение между провайдерами без перезапуска
- **Проверка доступности**: Автоматическая проверка наличия API ключа при выборе провайдера
- **Универсальность**: Поддержка множества провайдеров и моделей
- **Удобство**: Профили для разных окружений (dev, prod)
- **Централизованные настройки**: Глобальные параметры `temperature` и `max_tokens`

### Преимущества архитектуры

1. **Безопасность**: Ключи никогда не хранятся в переменных класса, читаются только при необходимости
2. **Явная проверка**: Невозможно выбрать провайдера без API ключа
3. **Простота использования**: Один метод `get_api_key()` для получения ключа при вызове API
4. **Расширяемость**: Легко добавлять новых провайдеров и модели
5. **Горячая перезагрузка**: Изменения конфигурации без перезапуска приложения

### Рекомендации по использованию

1. Всегда добавляйте `.env` в `.gitignore`
2. Используйте разные профили для разных окружений
3. Проверяйте доступность провайдера перед переключением с помощью `is_provider_available()`
4. Логируйте все переключения провайдеров для отладки
5. Валидируйте конфигурацию при старте приложения
6. Используйте `get_api_key()` непосредственно перед API вызовом, не сохраняйте ключ в переменных

Система готова к использованию и может быть легко расширена новыми провайдерами и функциональностью.
