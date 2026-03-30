# mobile_tariffs_tests

UI-автотесты проверки блока мобильных тарифов на лендингах MTS, Beeline, Megafon и T2.

## Стек

| Инструмент       | Версия  | Роль                          |
|-----------------|---------|-------------------------------|
| Python          | 3.10+   | Язык                          |
| pytest          | 7.4+    | Test runner                   |
| playwright      | 1.40+   | UI-взаимодействие (Chromium)  |
| allure-pytest   | 2.13+   | Отчёт                         |
| pytest-timeout  | 2.2+    | Таймаут на тест               |

---

## Установка

```bash
# 1. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 2. Поставить зависимости
pip install -r requirements.txt

# 3. Установить браузер Playwright
playwright install chromium
```

---

## Запуск

### Smoke (первые 3 карточки — по умолчанию)
```bash
pytest
```

### Все карточки (full run)
Откройте `tests/test_mobile_tariffs.py` и установите:
```python
SMOKE_CARD_LIMIT = None
```

### Отдельный лендинг по имени
```bash
pytest -k "MTS mts-home-gpon.ru"
```

### Только определённый оператор
```bash
pytest -k "Beeline"
```

### С Allure-отчётом
```bash
# Прогон
pytest --alluredir=allure-results

# Открыть отчёт в браузере
allure serve allure-results
```

---

## Структура проекта

```
mobile_tariffs_tests/
├── config/
│   ├── __init__.py
│   └── landing_data.py       # URL и селекторы для всех 10 лендингов
├── utils/
│   ├── __init__.py
│   └── helpers.py            # TestLogger + allure_attach_screenshot
├── tests/
│   └── test_mobile_tariffs.py # Основной тест
├── conftest.py               # Playwright fixtures + pytest_generate_tests
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## Тестовые данные

Все URL и селекторы хранятся в `config/landing_data.py` в виде списка словарей `LANDINGS`.
Для добавления нового лендинга достаточно добавить словарь в список — тест подхватит его автоматически.

| Поле                    | Пример                                  |
|-------------------------|-----------------------------------------|
| `name`                  | `"MTS mts-home-gpon.ru"`               |
| `url`                   | `"https://mts-home-gpon.ru/"`           |
| `nav_selector`          | `"a[href='/moskva/mobilnaya-svyaz#mobile']"` |
| `nav_text`              | `"Мобильная связь"`                    |
| `card_button_selector`  | `".button-mobile-application"`          |
| `expected_redirect_type`| `"new_tab"` / `"same_tab"` / `"either"` |
| `comment`               | Примечание по особенностям              |

---

## Allure: что сохраняется

- **Шаги** — каждый шаг сценария виден в Allure Timeline
- **Скриншот** — full-page после открытия раздела (+ при падении)
- **test_log** — полный текстовый лог теста
- **card_count** — количество найденных карточек
- **redirect_card_N** — URL редиректа каждой кнопки

---

## Telegram-алерты

Тест поддерживает два уровня уведомлений:

1. **Step-alert в момент падения шага** (отправляется из теста до `pytest.fail`)
2. **Итоговый summary по прогону** (отправляется после завершения run)

Нужны переменные окружения:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `RUN_URL` (ссылка на GitHub Actions run)

---

## GitHub Actions (ежедневно после основного теста)

Подготовлен workflow:

`mobile_tariffs_tests/.github/workflows/mobile-tariffs.yml`

Если вы добавляете папку `mobile_tariffs_tests` в существующий репозиторий
(а не как отдельный репозиторий), workflow-файл нужно положить в корень
репозитория: `.github/workflows/mobile-tariffs.yml`.

Он умеет:

- запускаться **после завершения** workflow `Playwright Tests` (`workflow_run`)
- запускаться вручную (`workflow_dispatch`)
- отправлять step-alert во время падения шага
- отправлять итоговый Telegram summary
- сохранять `allure-results` и `allure-report` как артефакты

Для работы в репозитории добавьте Secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

---

## Критерии падения

Тест падает, если:
- сайт не открылся (таймаут/ошибка загрузки)
- элемент навигации не найден или не кликается
- текст навигации не совпадает с ожидаемым
- карточки не появились после клика
- кнопка «Подключить» не инициировала редирект
- новая вкладка открылась пустой (`about:blank`)

---

## Замечания по лендингам

- **internet-mts-home.online** — в ТЗ URL без протокола; тест использует `https://`.
- **Beeline** — переход через `.cards-block-tab-button-mobile` (таб внутри блока тарифов).
- **Megafon** — переход через `button[data-pane='mobile']`; текст «Мобильные тарифы».
- **T2** — навигация `.click-mobile-trigger`; кнопки CTA ведут на t2.ru с UTM.
- **MTS new_tab** — кнопки «Подключить» открываются в новой вкладке (`target="_blank"`).
