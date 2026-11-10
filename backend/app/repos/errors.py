"""Domain errors shared by repositories."""

from __future__ import annotations


class UnknownRefs(ValueError):
    """Referenced tool/skill does not exist or is disabled."""
