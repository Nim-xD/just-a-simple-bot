import logging
import sentry_sdk
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

import config


def setup_sentry() -> None:
    sentry_logging = LoggingIntegration(level=logging.DEBUG, event_level=logging.WARNING)

    sentry_sdk.init(
        config.SENTRY_LINK,
        integrations=[sentry_logging, RedisIntegration()],
    )
