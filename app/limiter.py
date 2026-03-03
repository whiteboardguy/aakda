"""
limiter.py — shared SlowAPI rate-limiter instance.

Defined here (rather than in aakda.py) to avoid circular imports between
aakda.py and the route modules that need to apply @limiter.limit decorators.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
