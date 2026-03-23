def pytest_addoption(parser):
    parser.addoption(
        "--site",
        action="store",
        default=None,
        help="Домен сайта из SITE_CONFIGS, например: mts-home-gpon.ru",
    )
