"""Production settings for the isolated competition replay."""
from .settings import *  # noqa: F403

if not IS_PRODUCTION or DATABASES["default"]["NAME"] != "competition_review":  # noqa: F405
    raise RuntimeError("Competition review requires its dedicated production database.")

COMPETITION_REVIEW_MODE = True
MIDDLEWARE = [*MIDDLEWARE, "operations.competition_review.ReviewPermissions"]  # noqa: F405
