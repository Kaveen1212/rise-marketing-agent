"""
app/models/__init__.py
─────────────────────────────────────────────────────────────────────────────
Import all models here so that Alembic's env.py discovers them via
Base.metadata when running autogenerate.

If you add a new model file, add its import here.
─────────────────────────────────────────────────────────────────────────────
"""

from app.models.brief import PosterBrief, PosterStatus  # noqa: F401
from app.models.version import PosterVersion             # noqa: F401
from app.models.review import PosterReview, ReviewDecision  # noqa: F401
from app.models.publication import PosterPublication, PublicationStatus  # noqa: F401

__all__ = [
    "PosterBrief",
    "PosterStatus",
    "PosterVersion",
    "PosterReview",
    "ReviewDecision",
    "PosterPublication",
    "PublicationStatus",
]
