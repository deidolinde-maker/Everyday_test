# Everyday_test

Полная документация по текущей ветке `master` репозитория:
`https://github.com/deidolinde-maker/Everyday_test.git`.

Проект состоит из двух независимых наборов UI-автотестов:
1. Проверка форм заявок на лендингах провайдеров (корень репозитория).
2. Проверка блока мобильных тарифов (`mobile_tariffs_tests/`).

## 1. Структура репозитория

- `test_universal2.py`: основной тест форм заявок.
- `conftest.py`: параметр `--site` + screenshot в Allure при падении.
- `notify_from_allure.py`: сбор summary из `allure-results` и подготовка Telegram-уведомления.
- `mobile_tariffs_tests/tests/test_mobile_tariffs.py`: основной тест мобильных тарифов.
- `mobile_tariffs_tests/config/landing_data.py`: конфиг лендингов и ожиданий редиректа.
- `mobile_tariffs_tests/conftest.py`: фикстуры Playwright и параметризация по `LANDINGS`.
- `mobile_tariffs_tests/utils/helpers.py`: логирование, Allure-вложения, Telegram step-alert.
- `mobile_tariffs_tests/notify_from_allure_mobile.py`: итоговое Telegram summary для mobile suite.
- `.github/workflows/allure.yml`: CI для тестов форм.
- `.github/workflows/mobile-tariffs.yml`: CI для mobile tariffs.

## 2. Suite A: Тест форм заявок (`test_universal2.py`)

### Назначение
Проверка работоспособности форм (главная, popup, `/business`, городские версии сайтов) с реальной отправкой заявок.

### Главный сценарий `run_site_scenario`
1. `checkaddress` (если `has_checkaddress=True`).
2. Попапы главной.
3. Попапы `/business` (если `has_business=True`).
4. Выбор города (если `city_name` задан).
5. Повтор попапов для города: `4a` главная, `4b` `/business`.

### Как определяется успех отправки
`wait_for_success_url()` ждёт до 15 секунд, что URL содержит один из маркеров:
- `/tilda/form1/submitted`
- `/thanks`

Если маркер не появился, фиксируется `no_confirmation`.

### Основные конфиги
- `FORM_CONFIGS`: селекторы полей/submit по типам форм.
- `SITE_CONFIGS`: список доменов и флаги (`has_checkaddress`, `has_business`, `city_name`, `has_name_field`).
- `POPUP_CONTAINER_SELECTORS`, `SUGGESTION_SELECTORS`: устойчивость к разной вёрстке.

### Алерты и диагностика
- `log_error(...)`: тех-алерт по конкретному сбою.
- `send_step_alert(...)`: алерт по итогу шага.
- `conftest.py`: screenshot в Allure на падении теста.

## 3. Suite B: Мобильные тарифы (`mobile_tariffs_tests/`)

### Назначение
Проверка блока мобильных тарифов на лендингах MTS/Beeline/Megafon/T2.

### Главный сценарий `test_mobile_tariffs`
1. Открыть сайт.
2. Закрыть pop-up региона (если есть).
3. Принять cookies.
4. Перейти в раздел мобильных тарифов и проверить текст навигации.
5. Проверить, что карточки появились.
6. Прокликать CTA "Подключить" у карточек.
7. Проверить тип результата клика:
   - `new_tab` (новая вкладка),
   - `same_tab` (редирект в текущей),
   - `modal` (модалка),
   - `either` / `any` как разрешающие режимы.

По умолчанию smoke-режим: `SMOKE_CARD_LIMIT = 3` карточки.

### Конфигурация лендингов
`mobile_tariffs_tests/config/landing_data.py` содержит:
- `name`, `url`,
- `nav_selector`, `nav_text`,
- `card_button_selector`,
- `expected_redirect_type`,
- `comment`.

Актуально для `master`: на части лендингов ожидаемый тип редиректа изменён на `either`.

## 4. CI/CD (GitHub Actions)

### 4.1 `allure.yml` (формы)
Триггеры:
- `workflow_dispatch` (опционально `site`),
- `schedule` по cron `0 5 * * *` (05:00 UTC, что соответствует 08:00 по Москве),
- `push` в `main/master`.

Пайплайн:
1. Установка Python и зависимостей.
2. Установка Chromium.
3. Запуск `pytest test_universal2.py`.
4. Публикация артефактов `allure-results`.
5. Генерация и публикация отчёта в `gh-pages`.
6. Формирование и отправка Telegram summary.

### 4.2 `mobile-tariffs.yml` (мобильные тарифы)
Триггеры:
- `workflow_dispatch` с `landing_filter`,
- `workflow_run` после успешного завершения workflow `Playwright Tests`.

Пайплайн:
1. Установка зависимостей из `mobile_tariffs_tests/requirements.txt`.
2. Запуск mobile-тестов.
3. Сохранение `allure-results` и `allure-report` как artifacts.
4. Отправка Telegram summary через `notify_from_allure_mobile.py`.
5. Финальное падение job, если тесты неуспешны.

### 4.3 Во сколько запускается на сервере
- Сервер GitHub Actions живёт по UTC.
- Автозапуск `allure.yml` по cron `0 5 * * *`: каждый день в `05:00 UTC` (`08:00 МСК`).
- `mobile-tariffs.yml` не имеет своего cron.
- Он запускается либо вручную (`workflow_dispatch`), либо автоматически после успешного `Playwright Tests` (`workflow_run`), поэтому фиксированного серверного времени у него нет.

## 5. Структура Telegram-алертов

### 5.1 Suite форм (`test_universal2.py`)
`send_step_alert(...)` (по шагам):
```text
❌ [<site_label>] Шаг <step_no>: <step_name> — failed
Статус: failed
Причина: <reason>
URL: <page.url>
Время: <HH:MM:SS>
Run: <RUN_URL>                 # если переменная задана
```

`log_error(...)` (технический алерт):
```text
❌ Ошибка в тесте

Сайт: <site_label>
Ошибка: <error_msg>
Причина: <reason>
Детали: <extra>                # опционально
URL: <page.url>
Время: <HH:MM:SS>
Run: <RUN_URL>                 # если переменная задана
```

`notify_from_allure.py` (итоговый summary):
```text
✅ Прогон завершён успешно      # или ❌ Прогон завершён с ошибками

Сайт: <SITE_HINT>              # если передан
✅ Успешно: <passed>
❌ Упало: <failed>
Упавшие тесты:
  • <name1>
  • <name2>
Run: <RUN_URL>                 # если задан
Allure: <ALLURE_URL>           # если задан
```

### 5.2 Suite mobile (`mobile_tariffs_tests`)
`utils/helpers.py -> send_step_alert(...)`:
```text
❌ [<landing_name>] <step_name> — failed
Статус: failed
Причина: <reason>
URL: <page.url>
Время: <HH:MM:SS>
Run: <RUN_URL>                 # если переменная задана
```

`notify_from_allure_mobile.py` (итоговый summary):
```text
✅ Прогон завершён успешно      # или ❌ Прогон завершён с ошибками

Всего: <total>
✅ Успешно: <passed>
❌ Упало: <failed>
⚪ Пропущено: <skipped>
Упавшие тесты:
- <name1>
- <name2>
Run: <RUN_URL>                 # если задан
Allure: <ALLURE_URL>           # если задан
```

## 6. Локальный запуск

### 6.1 Формы (корень репозитория)
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install requests pytest-timeout
python -m playwright install chromium
```

Все сайты:
```bash
python -m pytest test_universal2.py -s --alluredir=allure-results --timeout=600
```

Один сайт:
```bash
python -m pytest test_universal2.py -s --site=mts-home.online --alluredir=allure-results --timeout=600
```

### 6.2 Мобильные тарифы
```bash
cd mobile_tariffs_tests
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pytest
```

Фильтр по лендингу:
```bash
python -m pytest -k "MTS mts-home.online"
```

## 7. Переменные окружения

Для Telegram/ссылок используются:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `RUN_URL`
- `ALLURE_RESULTS_DIR`
- `ALLURE_URL`
- `SITE_HINT` (только для suite форм)

## 8. Эксплуатация и поддержка

### Добавить новый сайт в suite форм
1. Добавить запись в `SITE_CONFIGS` в `test_universal2.py`.
2. При необходимости расширить `FORM_CONFIGS`/селекторы.
3. Прогнать локально `--site=<домен> --headed`.

### Добавить новый лендинг в suite mobile
1. Добавить запись в `mobile_tariffs_tests/config/landing_data.py`.
2. Проверить `nav_selector`, `card_button_selector`, `expected_redirect_type`.
3. Прогнать локально через `-k`.

### Быстрый разбор падения
1. Шаг/стадия падения в логах pytest.
2. Текст ошибки (`no_confirmation`, redirect mismatch и т.д.).
3. URL до/после шага.
4. Allure-вложения (скриншоты, лог, attach карточки).


