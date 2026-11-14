"""Keep downstream response bodies out of persisted Durable exceptions."""

import functools
import logging
import time


class ActivityFailure(RuntimeError):
    pass


def safe_activity(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        start = time.monotonic()
        ref = args[0] if args and isinstance(args[0], dict) else {}
        try:
            result = function(*args, **kwargs)
            logging.getLogger("indexadillo").info(
                "activity_completed stage=%s document_id=%s duration_ms=%.1f",
                function.__name__,
                ref.get("document_id", "collection"),
                (time.monotonic() - start) * 1000,
            )
            return result
        except Exception as exc:
            raise ActivityFailure(f"{function.__name__}: {type(exc).__name__}") from None

    return wrapped
