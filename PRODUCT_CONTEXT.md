# PRODUCT_CONTEXT
Обновлено: 2026-04-13

## 1. Общее описание продукта
- Продукт: репозиторий автотестов `Everyday_test` для проверки лендингов интернет-провайдеров.
- Состоит из двух независимых test-suite:
  - Suite A: проверка форм заявок (`test_universal2.py`).
  - Suite B: проверка блока мобильных тарифов (`mobile_tariffs_tests/`).
- Результаты публикуются в Allure; уведомления отправляются в Telegram.

## 2. Цели и ценность
- Рано обнаруживать регрессии на боевых лендингах.
- Проверять, что ключевые пользовательские действия работают:
  - открытие/заполнение/submit форм;
  - переход в раздел мобильных тарифов и поведение CTA.
- Выявлять недоступность сайтов и не блокировать общий прогон по всем доменам.
- Давать операционные сигналы через step/tech/critical alert.

## 3. Основные сущности
- `Site` (Suite A): запись в `SITE_CONFIGS` (домен + флаги сценария).
- `Landing` (Suite B): запись в `LANDINGS` (url, nav/card селекторы, ожидаемый redirect type).
- `Form type` (Suite A): `checkaddress`, `connection`, `profit`, `express-connection`, `business`.
- `Popup cycle`: последовательный прогон кнопок, открывающих формы.
- `City scenario`: выбор города + повторная проверка попапов для городского URL.
- `Alert`:
  - `step` (падение шага),
  - `tech` (точечная техническая ошибка),
  - `critical` (подтвержденная недоступность сайта).
- `Allure artifacts`: result json, attachments, screenshot_on_failure, текстовые вложения.
- `Redirect type` (Suite B): `new_tab`, `same_tab`, `modal`, `either`, `any`.

## 4. Пользовательские роли
- Инженер QA/автотестов:
  - запускает тесты локально и в CI;
  - анализирует падения по логам/Allure/Telegram.
- Разработчик/поддержка лендингов:
  - получает сигналы о поломках функционала.
- Аналитик/операционный пользователь отчетов:
  - использует итоговые статусы прогонов.
- Владелец продукта/бизнес-пользователь: `Не определено`.
- Формальный список ответственных за алерты Telegram: `Не определено`.

## 5. Бизнес-логика
- Suite A (`test_universal2.py`):
  - сценарий по сайту: шаги `1 -> 2 -> 3 -> 4 -> 4a -> 4b`;
  - success submit: URL содержит `/tilda/form1/submitted` или `/thanks`;
  - submit проверяется с retry и grace-периодом;
  - критическая недоступность сайта:
    - `HTTP >= 400`, или
    - суммарная неуспешная навигация `>= 60 сек`;
  - при critical сайт скипается (`pytest.skip`), прогон продолжается по следующим сайтам;
  - некритические ошибки (popup not found, no_confirmation, city issues) не переводятся в critical.
- Suite B (`mobile_tariffs_tests`):
  - открыть лендинг -> закрыть региональный popup -> принять cookies -> перейти в мобильный раздел;
  - проверить карточки и CTA;
  - классифицировать результат CTA по redirect type;
  - для лендингов с `expected_url_contains` дополнительно проверять целевой URL CTA по обязательным фрагментам;
  - падение шага отправляет step-alert.

## 6. Ключевые пользовательские сценарии
- Локальный прогон всех сайтов Suite A.
- Локальный прогон одного сайта Suite A через `--site=<domain>`.
- Локальный/CI прогон mobile suite полностью или с `landing_filter`.
- Анализ падения:
  - traceback pytest,
  - Allure attachments,
  - step/tech/critical сообщения в Telegram.
- Добавление нового домена/лендинга:
  - Suite A: обновление `SITE_CONFIGS` (+ селекторы при необходимости),
  - Suite B: обновление `LANDINGS`.

## 7. Интерфейсы и разделы продукта
- Интерфейсы запуска и наблюдения:
  - CLI (`pytest`),
  - GitHub Actions workflows,
  - Allure report (артефакты + gh-pages),
  - Telegram chat для алертов.
- Проверяемые разделы целевых сайтов (Suite A):
  - главная страница,
  - popup-формы,
  - `/business` (если применимо),
  - сценарий выбора города.
- Проверяемые разделы (Suite B):
  - блок мобильных тарифов,
  - карточки тарифов,
  - кнопки CTA "Подключить".

## 8. Интеграции
- Playwright (browser automation, Chromium).
- Pytest + плагины (`pytest-playwright`, `pytest-timeout`, `allure-pytest`).
- Allure (локально и в CI).
- Telegram Bot API:
  - Suite A: step/tech/critical и summary;
  - Suite B: step-alert и summary.
- GitHub Actions + GitHub Pages (публикация отчета).
- Внешние домены провайдеров (из `SITE_CONFIGS` и `LANDINGS`).
- Интеграция с Advizer в коде: `Не определено` (используется как ручная сверка процесса).

## 9. Технические особенности
- Язык: Python.
- Основной test-suite A:
  - конфиг доменов: `SITE_CONFIGS` (23 сайта на 2026-04-13),
  - таймауты/ретраи:
    - `NAV_GOTO_TIMEOUT_MS=20000`,
    - `NAV_RETRIES=3`,
    - `SITE_UNAVAILABLE_THRESHOLD_MS=60000`,
    - `SUBMIT_CONFIRM_TIMEOUT_MS=25000`,
    - `SUBMIT_CONFIRM_GRACE_MS=2000`.
- Suite A включает fallback-селекторы для:
  - cookies,
  - region popup,
  - city button/input/link.
- Suite A содержит антифлак для city redirect:
  - если URL уже сменился, выбор города считается успешным даже при timeout клика.
- Suite A сохраняет детальную диагностику popup-ошибок в Allure:
  - attachment `POPUP/BUSINESS failure details`,
  - `first_fail` в step-alert и assertion.
- `conftest.py` (корень) добавляет `screenshot_on_failure`.
- Suite B:
  - smoke-режим `SMOKE_CARD_LIMIT=3`,
  - redirect type validation,
  - опциональная URL-валидация CTA через `expected_url_contains` в `LANDINGS`,
  - отдельный browser context на каждый тест.

## 10. Текущее состояние проекта
- Основная ветка: `master`.
- Последние устойчивые изменения (по git log):
  - `6c677be`: диагностика popup-fail (`first_fail`, Allure failure details),
  - `bad6977`: fallback селекторы города/региона + антифлак city redirect,
  - `2b0659f`: обновление городских настроек и домена T2,
  - `a9d1a58`: отключен `/business` для `rt-internet.online` и `rtk-home-internet.ru`.
- CI:
  - `allure.yml` (формы): schedule `0 5 * * *`, workflow_dispatch (без автозапуска по push).
  - `mobile-tariffs.yml`: только `workflow_dispatch`, публикация Allure в `gh-pages/mobile-tariffs`.
- Количество конфигов на 2026-04-13:
  - Suite A: 23 сайта,
  - Suite B: 10 лендингов.

## 11. Правила изменений
- Источник правды по поведению тестов: код (`test_universal2.py`, `mobile_tariffs_tests/*`), затем документация.
- Любые изменения в продуктовой логике тестов:
  - обновлять этот файл,
  - не добавлять недоказанные факты,
  - неизвестное помечать `Не определено`,
  - спорное заносить в раздел `Требует уточнения`.
- При изменении доменов/селекторов:
  - фиксировать причину изменения,
  - делать точечные прогоны по затронутым доменам,
  - проверять Allure attachments и текст step-alert.
- Для outage-логики:
  - не расширять critical-критерии без явного согласования.

## 12. Требует уточнения
- Официальный SLA доступности лендингов и допустимые окна деградации.
- Финальный список получателей и каналов для `critical` алертов.
- Нужна ли обратная совместимость для старых `--site` алиасов (пример: старый T2-домен).
- Нужно ли переводить предупреждение `Поле Имя не найдено` в fail для некоторых сайтов.
- Нужно ли хранить и версионировать эталонные селекторы отдельно от тестового кода.
- Нужна ли официальная поддержка запуска в Windows cp1251 без `PYTHONIOENCODING=utf-8`.
- Явная политика для “флаков” (авторетрай в CI, quarantine, доп. метки в Allure): `Не определено`.
