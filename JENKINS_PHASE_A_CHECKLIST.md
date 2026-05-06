# Jenkins Phase A Checklist (smoke mobile)

Обновлено: 2026-05-06

## Цель фазы

Быстро проверить Jenkins-рантайм на самом чувствительном наборе:

- провайдеры: `domru`, `t2` (`PROVIDER_SCOPE=smoke`)
- режим: `core`
- mobile профили: `mobile-chromium` + `mobile-webkit`

## Параметры запуска job

- `PROVIDER_SCOPE=smoke`
- `SERVICE_MODE=core`
- `RUN_CHROMIUM=false`
- `RUN_FIREFOX=false`
- `RUN_WEBKIT=false`
- `RUN_MOBILE_CHROMIUM=true`
- `RUN_MOBILE_WEBKIT=true`
- `BLOCKING_PROFILE=none`
- `SITE=` (пусто)

## Что проверить в логе Jenkins

1. Кеш путь определился:
   - `PLAYWRIGHT_BROWSERS_PATH=/var/lib/jenkins/cache/ms-playwright`
2. Нет постоянной перезакачки браузеров:
   - при повторном запуске должны быть сообщения `already exists in shared cache`.
3. Запускаются именно mobile прогоны:
   - `--execution-profile=mobile-chromium`
   - `--execution-profile=mobile-webkit`
4. Provider scope действительно smoke:
   - в логах идут только `domru` и `t2`.

## Ожидаемый результат

- прогон завершается зеленым статусом,
- собирается директория `allure-results`,
- артефакты `allure-results/**` доступны в Jenkins.

## Быстрые проверки при падении

1. Проверить доступность кеш-каталога:
   - права на `/var/lib/jenkins/cache/ms-playwright`.
2. Проверить, что включен хотя бы один браузерный флаг.
3. Проверить, что на ноде установлен `python3` и доступен `pip`.
4. Проверить сетевую доступность сайтов провайдеров с Jenkins-ноды.

## Критерий готовности к Фазе B

- два подряд успешных smoke запуска на Jenkins
- без повторной загрузки браузеров на втором запуске.
