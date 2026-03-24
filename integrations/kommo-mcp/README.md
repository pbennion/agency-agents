# Kommo CRM MCP Server

MCP-сервер для работы с [Kommo CRM](https://www.kommo.com/) через Claude Desktop.

## Возможности

28 инструментов в 11 группах:

| Группа | Инструменты |
|--------|-------------|
| **Leads** | list, get, create, update, delete |
| **Contacts** | list, get, create, update |
| **Companies** | list, get, create, update |
| **Tasks** | list, create, update |
| **Notes** | list, create |
| **Pipelines** | list, get |
| **Users** | list, get |
| **Custom Fields** | list |
| **Tags** | list, create |
| **Events** | list |
| **Calls** | add |

---

## Установка

### Windows — автоматически (рекомендуется)

1. Скачай файл [`install-windows.bat`](./install-windows.bat) из этого репозитория
2. Запусти **от имени администратора** (правой кнопкой → «Запустить от имени администратора»)
3. Скрипт сам:
   - Проверит Python и установит зависимости
   - Клонирует репозиторий (или скачает ZIP, если git не установлен)
   - Спросит `KOMMO_TOKEN` и `KOMMO_SUBDOMAIN`
   - Пропишет конфиг в Claude Desktop
4. Перезапусти Claude Desktop — готово

> **Требования:** Python 3.10+ с галочкой «Add Python to PATH» при установке, Claude Desktop

---

### macOS / Linux — вручную

#### 1. Клонировать репозиторий

```bash
git clone https://github.com/NatrixAi/kommo-mcp.git
cd kommo-mcp
```

#### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

#### 3. Получить токен Kommo

В Kommo CRM: **Настройки → Интеграции → API → Долгосрочный токен**

#### 4. Добавить в Claude Desktop

Открыть конфиг Claude Desktop:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Добавить:

```json
{
  "mcpServers": {
    "kommo": {
      "command": "python3",
      "args": ["/path/to/kommo-mcp/server.py"],
      "env": {
        "KOMMO_TOKEN": "ваш_долгосрочный_токен",
        "KOMMO_SUBDOMAIN": "ваш_субдомен"
      }
    }
  }
}
```

> На Windows команда `python` вместо `python3`, путь через двойные слэши: `C:\\Users\\user\\kommo-mcp\\server.py`

> **KOMMO_SUBDOMAIN** — часть URL. Если адрес `mycompany.kommo.com`, то субдомен = `mycompany`.

#### 5. Перезапустить Claude Desktop

---
## Переменные окружения

| Переменная | Описание | Пример |
|------------|----------|--------|
| `KOMMO_TOKEN` | Долгосрочный токен API | `eyJ0eXAi...` |
| `KOMMO_SUBDOMAIN` | Субдомен аккаунта | `mycompany` |

## Примеры использования

```
Покажи все открытые лиды в воронке "Новые клиенты"
Создай контакт: Иван Иванов, телефон +7 999 123-45-67
Добавь задачу: позвонить лиду #12345 завтра в 10:00
Покажи все теги для лидов
Какие кастомные поля есть у контактов?
Добавь запись о звонке: 5 минут, входящий, телефон +7 999 000-00-00
```

## Требования

- Python 3.10+
- Claude Desktop
- Аккаунт Kommo CRM с API-доступом

## Лицензия

MIT
