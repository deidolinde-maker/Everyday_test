# PB3 Final Acceptance Report
Дата: 2026-04-29
Статус: условно принят (go-live), freeze с остаточным условием stability-soak

## 1. Область приёмки (P3-R12)
- Проверка паритета и работоспособности нового провайдерного контура.
- Проверка, что основной запуск выполняется через `provider-orchestrator.yml`.
- Проверка, что legacy-автозапуск отключен и не конфликтует с новым контуром.
- Проверка актуальности документации.

## 2. Фактические результаты
1. Успешный полный прогон оркестратора:
   - Run: `Provider Orchestrator`
   - URL: https://github.com/deidolinde-maker/Everyday_test/actions/runs/25095072405
   - Статус: `completed/success`
   - UTC окно: `2026-04-29T06:53:11Z` -> `2026-04-29T08:22:50Z`
   - Провайдерные jobs: MTS, Beeline, Megafon, T2, Rostelecom, Domru — все `success`.
2. Локальный минимальный test-gate:
   - `python -m pytest --collect-only -q test_universal2.py` -> `23 tests collected`.
   - `python -m pytest --collect-only -q mobile_tariffs_tests/tests/test_mobile_tariffs.py` -> `10 tests collected`.
3. CI-контур после миграции:
   - legacy `allure.yml` переведен в ручной режим (`workflow_dispatch`, без `schedule`);
   - `mobile-tariffs.yml` переведен в ручной режим (`workflow_dispatch`, без `workflow_run`);
   - основной путь массового прогона: `provider-orchestrator.yml`.
4. Документация синхронизирована:
   - `README.md` обновлен под новый запускной контур;
   - `PRODUCT_CONTEXT.md` обновлен под фактические триггеры CI.

## 3. Выполненные релизы PB3 (ключевые)
- `ff550b4` — provider split + provider workflows + orchestrator tuning.
- `33b4341` — фикс city/thanks возврата для стабильности MTS в core/chromium.
- `ac398d6` — отключение legacy-автозапусков.
- `0e7055e` — документация под новый CI-контур.

## 4. Критерии P3-R12 и статус
1. Паритет и работоспособность на контрольной выборке: `Выполнено`.
2. Стабильные точечные/провайдерные прогоны: `Выполнено` (подтверждено orchestrator run).
3. Документация актуальна: `Выполнено`.
4. 3 последовательных дня без критичных регрессий: `Не закрыто` (нужен наблюдаемый период).

## 5. Остаточный риск и условие freeze
- Остаточный риск: возможные флаки на отдельных лендингах при смене верстки/редиректов.
- Условие полного закрытия P3-R12:
  - выполнить stability-soak: 3 последовательных дня orchestrator прогона без критичных регрессий.

## 6. Решение
- PB3 принимается для текущей эксплуатации через `provider-orchestrator.yml`.
- Финальное полное закрытие пункта P3-R12: после выполнения 3-дневного stability-soak.
