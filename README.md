# Everyday_test

Актуальная документация для ветки `master` репозитория:
`https://github.com/deidolinde-maker/Everyday_test.git`.

Проект состоит из двух независимых наборов UI-автотестов:
1. Проверка форм заявок на лендингах провайдеров (корень репозитория, `test_universal2.py`).
2. Проверка блока мобильных тарифов (`mobile_tariffs_tests/`).

## 1. Структура репозитория

- `test_universal2.py` - основной e2e-тест форм (главная, popups, `/business`, городские сценарии).
- `conftest.py` - параметр `--site`, вложения в Allure при падении.
- `notify_from_allure.py` - итоговый summary по `allure-results` для Telegram.
- `mobile_tariffs_tests/tests/test_mobile_tariffs.py` - тест блока мобильных тарифов.
- `mobile_tariffs_tests/config/landing_data.py` - список лендингов mobile suite.
- `mobile_tariffs_tests/conftest.py` - фикстуры и параметризация по `LANDINGS`.
- `mobile_tariffs_tests/utils/helpers.py` - шаговые алерты/утилиты mobile suite.
- `mobile_tariffs_tests/notify_from_allure_mobile.py` - итоговый mobile summary в Telegram.
- `.github/workflows/allure.yml` - CI формы.
- `.github/workflows/mobile-tariffs.yml` - CI mobile suite.

## 2. Suite A: Формы заявок (`test_universal2.py`)

### 2.1 Что проверяет тест

Скрипт проверяет, что формы заявок на каждом сайте открываются, корректно заполняются и дают подтверждение отправки (URL содержит `/tilda/form1/submitted` или `/thanks`).

### 2.2 Пошаговый сценарий `run_site_scenario`

Для каждого сайта из `SITE_CONFIGS`:

1. Шаг 1 - `checkaddress` (если `has_checkaddress=True`):
   - переход на `base_url`,
   - поиск формы `checkaddress`,
   - заполнение улицы/дома/телефона (и имени, если требуется),
   - submit с подтверждением.
2. Шаг 2 - popups на главной:
   - сбор всех целевых кнопок,
   - последовательный цикл по каждой кнопке: открыть popup -> заполнить -> submit -> проверить подтверждение.
3. Шаг 3 - popups `/business` (если `has_business=True`):
   - аналогично шагу 2, но на `base_url + /business`.
4. Шаг 4 - выбор города (если `city_name` задан):
   - открыть селектор города,
   - найти нужный город в списке,
   - кликнуть и дождаться смены URL.
5. Шаг 4a - popups главной городского URL (если шаг 4 успешен).
6. Шаг 4b - popups `/business` городского URL (если `has_business=True` и шаг 4 успешен).

Если шаг неприменим по флагам, он помечается как `неприменим` и не считается ошибкой.

### 2.3 Логика навигации и защита от "упавшего" сайта

Используется `safe_goto(...)`:

- `NAV_RETRIES = 3` попытки.
- `NAV_GOTO_TIMEOUT_MS = 20_000` на каждую попытку.
- Критический инцидент (`critical`) только если:
  - сервер вернул `HTTP >= 400` (например, 400/403/500/502), или
  - суммарное время навигации достигло `SITE_UNAVAILABLE_THRESHOLD_MS = 60_000`.
- Если ошибка не критическая (например, кратковременный флак до 60с), шаг падает как обычный `failed`, но сайт не скипается целиком.
- Если ошибка критическая, вызывается `skip_site_due_unavailability(...)`:
  - отправляется `critical` алерт в Telegram,
  - текущий сайт помечается `pytest.skip(...)`,
  - прогон продолжается на следующем сайте.

Важно: `critical` не шлется на типовые функциональные ошибки вроде "не нашли popup", "не выбрали город", "не заполнилось поле".

### 2.4 Логика submit и подтверждения отправки

Подтверждение проверяется через `submit_with_confirmation(...)` + `wait_for_success_url(...)`:

- `SUBMIT_CONFIRM_TIMEOUT_MS = 25_000` (ожидание маркеров успеха).
- Дополнительный `SUBMIT_CONFIRM_GRACE_MS = 2_000` после основного ожидания.
- Если подтверждение не пришло, выполняется повторный submit (`attempts=2`).
- Учитывается редкий кейс, когда success-URL открылся в новой вкладке.

Это уменьшает ложные `no_confirmation` при медленных редиректах после submit.

### 2.5 Усиление выбора города (region selector)

`run_city_scenario(...)` использует набор fallback-локаторов и усиления:

- выбор только видимых (`is_visible`) кандидатов для кнопки города;
- до 3 попыток клика по кнопке города;
- поиск поля ввода города по нескольким селекторам;
- поиск ссылки города по нескольким селекторам + `has_text=city_name`;
- до 3 попыток клика по найденному городу;
- ожидание смены URL после клика.

Если город не найден/не кликнулся/URL не сменился - это шаговая ошибка (`step alert`), но не `critical`.

### 2.6 Ключевые конфиги Suite A

- `SITE_CONFIGS`:
  - ключ: домен (используется в `--site`),
  - значения:
    - `base_url`,
    - `has_checkaddress`,
    - `has_business`,
    - `city_name`,
    - `has_name_field` (опционально).
- `FORM_CONFIGS` - CSS-селекторы полей и submit по типам форм.
- `POPUP_CONTAINER_SELECTORS`, `SUGGESTION_SELECTORS` - fallback-локаторы для нестабильной верстки.

## 3. Telegram-алерты (Suite A)

### 3.1 Step alert (`send_step_alert`)

Шлется при падении шага (не критическая недоступность):

```text
❌ [<site_label>] Шаг <step_no>: <step_name> — failed
Статус: failed
Причина: <reason>
URL: <page.url>
Время: <HH:MM:SS>
Run: <RUN_URL>    # если задан
```

### 3.2 Tech alert (`log_error`)

Шлется по точечной технической ошибке внутри шага (`popup_not_found`, `no_confirmation` и т.д.):

```text
❌ Ошибка в тесте

Сайт: <site_label>
Ошибка: <error_msg>
Причина: <reason>
Детали: <extra>   # опционально
URL: <page.url>
Время: <HH:MM:SS>
Run: <RUN_URL>    # если задан
```

### 3.3 Critical alert (`send_critical_alert`)

Шлется только при подтвержденной недоступности сайта (HTTP 4xx/5xx или навигация >= 60с):

```text
[CRITICAL] [<site_label>] Шаг <step_no>: <step_name>
Статус: critical
Причина: <reason>
URL: <page.url>
Время: <HH:MM:SS>
Run: <RUN_URL>    # если задан
```

## 4. Suite B: Мобильные тарифы (`mobile_tariffs_tests/`)

### 4.1 Что проверяет тест

`test_mobile_tariffs`:
1. Открывает лендинг.
2. Закрывает мешающие popups/региональные оверлеи (если есть).
3. Принимает cookies.
4. Переходит в раздел мобильных тарифов и проверяет текст навигации.
5. Проверяет, что карточки загрузились.
6. Кликает CTA на карточках (smoke по ограниченному числу карточек).
7. Валидирует ожидаемый тип результата:
   - `new_tab`,
   - `same_tab`,
   - `modal`,
   - `either` / `any` (допускающие режимы).

### 4.2 Конфиг лендингов

`mobile_tariffs_tests/config/landing_data.py`:

- `name`,
- `url`,
- `nav_selector`,
- `nav_text`,
- `card_button_selector`,
- `expected_redirect_type`,
- `comment`.

## 5. CI/CD (GitHub Actions)

### 5.1 Формы: `.github/workflows/allure.yml`

Триггеры:
- `workflow_dispatch` (входной параметр `site`),
- `schedule: 0 5 * * *`,
- `push` в `main/master`.

Что делает:
1. Ставит Python и зависимости.
2. Ставит Chromium для Playwright.
3. Запускает `pytest test_universal2.py` (либо по одному `site`, либо все).
4. Собирает `allure-results`.
5. Генерирует Allure report и публикует в `gh-pages`.
6. Формирует и отправляет Telegram summary.

### 5.2 Mobile: `.github/workflows/mobile-tariffs.yml`

Триггеры:
- `workflow_dispatch` (входной параметр `landing_filter`),
- `workflow_run` после успешного `Playwright Tests`.

Что делает:
1. Ставит зависимости `mobile_tariffs_tests`.
2. Запускает mobile-тесты (полный прогон или `pytest -k "<landing_filter>"`).
3. Сохраняет `allure-results` и `allure-report` артефактами.
4. Отправляет Telegram summary.
5. Финально роняет job, если тесты упали.

### 5.3 Во сколько запускается на сервере

- GitHub Actions работает в UTC.
- Автозапуск `allure.yml` по cron `0 5 * * *`:
  - `05:00 UTC` каждый день,
  - `08:00` по Москве (MSK).
- `mobile-tariffs.yml` не имеет собственного cron:
  - запускается вручную,
  - или после успешного завершения workflow `Playwright Tests`.

## 6. Как добавить новый URL (подробно)

### 6.1 Добавить сайт в Suite A (формы)

1. Открыть `test_universal2.py`, блок `SITE_CONFIGS`.
2. Добавить новый ключ-домен и конфиг:

```python
"example-site.ru": {
    "base_url": "https://example-site.ru/",
    "has_checkaddress": False,
    "has_business": True,
    "city_name": "Москва",      # или None
    "has_name_field": False,    # опционально
},
```

3. Правила по полям:
   - `base_url` всегда с протоколом `https://`.
   - ключ словаря должен совпадать с тем, что будете передавать в `--site`.
   - если на сайте нет городского режима: `city_name=None`.
   - если нет `/business`: `has_business=False`.
4. Если у форм нестандартные классы:
   - добавить/обновить селекторы в `FORM_CONFIGS`,
   - при необходимости расширить fallback-селекторы.
5. Прогнать локально точечно:
   - `python -m pytest test_universal2.py -s --site=example-site.ru --alluredir=allure-results --timeout=600`
6. Проверить в логах:
   - успешные submit-подтверждения,
   - отсутствие ложных `critical`,
   - корректность шагов города/`/business`.

### 6.2 Добавить URL в ручной запуск CI для Suite A

В GitHub Actions -> `Playwright Tests` -> `Run workflow`:

1. В поле `site` указать домен-ключ из `SITE_CONFIGS` (например, `example-site.ru`).
2. Пустое поле `site` = прогон всех сайтов.

### 6.3 Добавить лендинг в Suite B (mobile)

1. Открыть `mobile_tariffs_tests/config/landing_data.py`.
2. Добавить объект в `LANDINGS`:

```python
{
    "name": "Provider example-site.ru",
    "url": "https://example-site.ru/",
    "nav_selector": "...",
    "nav_text": "Мобильная связь",
    "card_button_selector": "...",
    "expected_redirect_type": "either",
    "comment": "Короткое пояснение по особенностям лендинга",
},
```

3. Если в ТЗ URL без протокола - приводить к `https://...`.
4. Прогнать точечно:
   - `cd mobile_tariffs_tests`
   - `python -m pytest -k "example-site.ru"`

### 6.4 Добавить URL в ручной запуск CI для Suite B

В GitHub Actions -> `Mobile Tariffs Tests` -> `Run workflow`:

1. Поле `landing_filter` принимает выражение для `pytest -k`.
2. Пример: `MTS mts-home.online`.
3. Пустой `landing_filter` = полный прогон.

## 7. Локальный запуск

### 7.1 Suite A (формы)

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

### 7.2 Suite B (mobile)

```bash
cd mobile_tariffs_tests
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pytest
```

Точечный запуск:

```bash
python -m pytest -k "MTS mts-home.online"
```

## 8. Переменные окружения

Основные переменные:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `RUN_URL`
- `ALLURE_RESULTS_DIR`
- `ALLURE_URL`
- `SITE_HINT` (только для suite форм)

## 9. Быстрый разбор падения

1. Найти шаг падения (`Шаг 1/2/3/4/4a/4b`) в логах pytest.
2. Проверить тип ошибки:
   - `step/tech` (функциональный сбой),
   - `critical` (подтвержденная недоступность сайта).
3. Сверить URL до/после действия и статус submit-подтверждения.
4. Проверить Allure-вложения (скриншоты, текстовые attach шага/critical).

## 10. Как тестировался скрипт

### 10.1 Основной suite (формы, `test_universal2.py`)

1. Прогоны в терминале через видимый браузер (`--headed`) на отдельных доменах и на полном списке.
2. Сравнение факта отправки заявок в реальном времени в Advizer с действиями теста и URL подтверждения.
3. Отдельные прогоны в условиях недоступности части сайтов (timeouts/ошибки ответа) для проверки:
   - корректного срабатывания `critical` только при `HTTP >= 400` или навигации `>= 60с`,
   - пропуска недоступного сайта через `pytest.skip(...)`,
   - продолжения прогона по остальным сайтам.
4. Проверка ложноположительных сбоев submit:
   - редирект на thanks/submitted с задержкой,
   - подтверждение после grace-периода,
   - повторная попытка submit при `no_confirmation`.
5. Проверка устойчивости выбора города:
   - разные варианты кнопки открытия селектора,
   - случаи с медленной отрисовкой списка,
   - повторные попытки клика по кнопке города и по ссылке города.

### 10.2 Mobile suite (`mobile_tariffs_tests`)

1. Негативный сценарий: страница без блока мобильных тарифов (валидация понятной ошибки шага).
2. Негативный сценарий: блок мобильных тарифов есть, но карточек нет.
3. Фактический боевой прогон по рабочим лендингам из `LANDINGS`.
4. Проверка типов переходов CTA:
   - `new_tab`,
   - `same_tab`,
   - `modal`,
   - `either`/`any` для смешанных кейсов.

### 10.3 Инженерные проверки качества изменений

1. Code review diff перед пушем:
   - нет ли регрессий в существующих ветках сценария,
   - не задеты ли условия, которые должны оставаться некритичными.
2. Проверка консольных логов на каждом шаге:
   - понятность причины падения,
   - совпадение шага в логе, в алерте и в Allure.
3. Проверка Telegram-алертов:
   - `step/tech/critical` не смешиваются,
   - critical уходит только на подтвержденную недоступность сайта.
4. Проверка совместимости с CI:
   - локальный прогон по одному сайту (`--site`) и полный прогон,
   - соответствие README фактическим значениям таймаутов/ретраев из кода.
