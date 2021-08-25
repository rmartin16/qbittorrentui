import logging
from time import time


IS_TIMING_LOGGING_ENABLED = False
default_logger = logging.getLogger(__name__)


def log_keypress(logger=default_logger, obj: object = None, key: str = "unknown"):
    logger.info("%s received key '%s'", obj.__class__.__name__, key)


def log_timing(
    logger=default_logger,
    action: str = "Refreshing",
    obj: object = None,
    sender="unknown",
    start_time=time(),
):
    if IS_TIMING_LOGGING_ENABLED:
        logger.info(
            "%s %s (from %s) (%.2f)",
            action,
            obj.__class__.__name__,
            sender,
            (time() - start_time),
        )
    return True
