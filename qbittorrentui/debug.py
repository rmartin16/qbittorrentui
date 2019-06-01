import logging
from time import time


IS_TIMING_LOGGING_ENABLED = True


def log_keypress(logger=logging.getLogger(__name__), obj: object = None, key: str = 'unknown'):
    logger.info("%s received key '%s'" % (obj.__class__.__name__, key))


def log_timing(logger=logging.getLogger(__name__), action: str = "Refreshing", obj: object = None, sender='unknown', start_time=time()):
    if IS_TIMING_LOGGING_ENABLED:
        logger.info("%s %s (from %s) (%.2f)" % (action, obj.__class__.__name__, sender, (time() - start_time)))
