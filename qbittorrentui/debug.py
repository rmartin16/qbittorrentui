import logging


IS_TIMING_LOGGING_ENABLED = False


def log_keypress(logger: logging.getLogger(__name__), obj: object, key: str):
    logger.info("%s received key '%s'" % (obj.__class__.__name__, key))
