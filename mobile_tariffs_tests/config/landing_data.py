"""
Конфигурация тестовых данных для всех лендингов.
Каждый лендинг описывается набором атрибутов:
  - name: человекочитаемое имя для Allure и логов
  - url: полный URL лендинга
  - nav_selector: CSS-селектор элемента перехода в мобильный раздел
  - nav_text: ожидаемый текст элемента навигации (проверка "in")
  - card_button_selector: CSS-селектор кнопок «Подключить» на карточках
  - expected_redirect_type: 'new_tab' | 'same_tab' | 'either'
  - comment: короткая заметка об особенностях лендинга
"""

LANDINGS = [
    # ─────────────────── MTS ───────────────────
    {
        "name": "MTS mts-home-gpon.ru",
        "url": "https://mts-home-gpon.ru/",
        "nav_selector": "a[href='/moskva/mobilnaya-svyaz#mobile']",
        "nav_text": "Мобильная связь",
        "card_button_selector": ".button-mobile-application",
        "expected_redirect_type": "either",
        "comment": "Стандартный MTS лендинг. Переход по href на /moskva/mobilnaya-svyaz#mobile. Для CTA допускаем редирект в текущей или новой вкладке.",
    },
    {
        "name": "MTS mts-home.online",
        "url": "https://mts-home.online",
        "nav_selector": "a[href='/mobilnaya-svyaz']",
        "nav_text": "Мобильная связь",
        "card_button_selector": ".button-mobile-application",
        "expected_redirect_type": "either",
        # кнопка: button.button.button-red.card-one__button.button-mobile-application
        "comment": "Переход на /mobilnaya-svyaz. Кнопка имеет несколько классов, используем .button-mobile-application.",
    },
    {
        "name": "MTS mts-home-online.ru",
        "url": "https://mts-home-online.ru/",
        "nav_selector": "a[href='/moskva/mobilnaya-svyaz#mobile']",
        "nav_text": "Мобильная связь",
        "card_button_selector": ".button-mobile-application",
        "expected_redirect_type": "either",
        "comment": "Аналог mts-home-gpon.ru, тот же селектор навигации.",
    },
    {
        "name": "MTS internet-mts-home.online",
        "url": "https://internet-mts-home.online",
        "nav_selector": "a[href='#mobile']",
        "nav_text": "Мобильная связь",
        "card_button_selector": ".button-mobile-application",
        "expected_redirect_type": "either",
        # В ТЗ URL указан без протокола — добавляем https://
        "comment": "URL в ТЗ без протокола, используем https://. Навигация по якорю #mobile.",
    },
    # ─────────────────── Beeline ───────────────────
    {
        "name": "Beeline beeline-internet.online",
        "url": "https://beeline-internet.online/",
        "nav_selector": ".cards-block-tab-button-mobile",
        "nav_text": "Мобильная связь",
        "card_button_selector": ".card-block__button",
        "expected_redirect_type": "either",
        # href кнопки ведёт на https://mobile.101internet.ru/beeline
        "comment": "Переход через таб-кнопку внутри блока тарифов. CTA ведёт на 101internet.ru/beeline.",
    },
    {
        "name": "Beeline beeline-ru.online",
        "url": "https://beeline-ru.online/",
        "nav_selector": ".cards-block-tab-button-mobile",
        "nav_text": "Мобильная связь",
        "card_button_selector": ".card-block__button",
        "expected_redirect_type": "either",
        "comment": "Структура аналогична beeline-internet.online.",
    },
    {
        "name": "Beeline online-beeline.ru",
        "url": "https://online-beeline.ru/",
        "nav_selector": ".cards-block-tab-button-mobile",
        "nav_text": "Мобильная связь",
        # На этом сайте в мобильном блоке два вида карточек:
        #   1) конвергентные (.card-block__button без href) — открывают модалку
        #   2) чисто мобильные (a.card-block__button с href) — делают редирект
        # Берём только кнопки-ссылки с href через CSS :is(a).card-block__button
        "card_button_selector": "a.card-block__button",
        "expected_redirect_type": "same_tab",
        "comment": "Мобильные карточки имеют селектор a.card-block__button (с href). Кнопки без href открывают модалку — не проверяем.",
    },
    # ─────────────────── Megafon ───────────────────
    {
        "name": "Megafon mega-premium.ru",
        "url": "https://mega-premium.ru",
        "nav_selector": "button.tariffs-switch__tab[data-pane='mobile']",
        "nav_text": "Мобильные тарифы",
        "card_button_selector": ".card-mobile__button",
        "expected_redirect_type": "either",
        # href кнопки ведёт на https://mobile.101internet.ru/megafon
        "comment": "Переход через button с data-pane='mobile'. CTA ведёт на 101internet.ru/megafon.",
    },
    {
        "name": "Megafon mega-home-internet.ru",
        "url": "https://mega-home-internet.ru",
        "nav_selector": "button.tariffs-switch__tab[data-pane='mobile']",
        "nav_text": "Мобильные тарифы",
        "card_button_selector": ".card-mobile__button",
        "expected_redirect_type": "either",
        "comment": "Структура аналогична mega-premium.ru.",
    },
    # ─────────────────── T2 ───────────────────
    {
        "name": "T2 t2-ru.online",
        "url": "https://t2-ru.online/moskva",
        "nav_selector": ".click-mobile-trigger",
        "nav_text": "Мобильная связь",
        "card_button_selector": ".card-new__button",
        "expected_redirect_type": "new_tab",
        # Полный селектор: a[href="https://t2-ru.online/moskva/mobilnaya-svyaz/"].click-mobile-trigger
        # Кнопка ведёт на домен t2.ru с UTM-параметрами
        "comment": "Навигация через .click-mobile-trigger. CTA ведёт на t2.ru с UTM-параметрами.",
    },
      {
        "name": "Тестовая страница",
        "url": "https://mts-home-online.ru/testovaya-forms",
        "nav_selector": "a[href='/mobilnaya-svyaz']",
        "nav_text": "Мобильная связь",
        "card_button_selector": ".button-mobile-application",
        "expected_redirect_type": "either",
        # кнопка: button.button.button-red.card-one__button.button-mobile-application
        "comment": "Переход на /mobilnaya-svyaz. Кнопка имеет несколько классов, используем .button-mobile-application.",
    },
]
