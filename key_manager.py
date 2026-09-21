from config import settings
from utils.logger import get_logger
import time

logger = get_logger(__name__)

# Load all available keys
AVAILABLE_KEYS = [k for k in [
    settings.gemini_api_key,
    settings.gemini_api_key_fallback,
    settings.gemini_api_key_3,
    settings.gemini_api_key_4
] if k and k.strip()]

_current_key_idx = 0
_quick_unavailable_until = 0.0
QUICK_UNAVAILABLE_COOLDOWN_SECONDS = 300


class QuickModelUnavailableError(RuntimeError):
    """Raised when Gemini Flash is rate-limited on every configured key."""


def is_quota_error(error: Exception | str) -> bool:
    """Return whether an error indicates a provider quota or rate-limit failure."""
    error_text = str(error).lower()
    return any(marker in error_text for marker in (
        "429",
        "quota",
        "resource_exhausted",
        "exhausted",
        "rate limit",
    ))


def is_quick_temporarily_unavailable() -> bool:
    """Return whether Quick Thinking is in its short provider-cooldown window."""
    return time.monotonic() < _quick_unavailable_until


def mark_quick_temporarily_unavailable() -> None:
    """Pause Quick Thinking briefly after all Gemini keys are exhausted."""
    global _quick_unavailable_until
    _quick_unavailable_until = time.monotonic() + QUICK_UNAVAILABLE_COOLDOWN_SECONDS
    logger.error(
        "Gemini Flash quota exhausted on all configured keys. "
        "Quick Thinking unavailable for %ss.",
        QUICK_UNAVAILABLE_COOLDOWN_SECONDS,
    )


def clear_quick_temporarily_unavailable() -> None:
    """Clear a previous Quick Thinking cooldown after a successful request."""
    global _quick_unavailable_until
    _quick_unavailable_until = 0.0

def get_current_key() -> str:
    """Returns the currently active Gemini API key."""
    if not AVAILABLE_KEYS:
        logger.error("No Gemini API keys configured!")
        return ""
    return AVAILABLE_KEYS[_current_key_idx]

def rotate_key() -> bool:
    """
    Rotates to the next available API key.
    Returns True if successfully rotated to a new key, False if all keys exhausted.
    """
    global _current_key_idx
    if not AVAILABLE_KEYS:
        return False
        
    _current_key_idx += 1
    if _current_key_idx >= len(AVAILABLE_KEYS):
        # We've exhausted all keys. Wrap around but return False to indicate failure
        _current_key_idx = 0
        logger.error("All API keys exhausted. Wrapping around to the first key.")
        return False
        
    logger.warning(f"Rotated API key. Now using key index #{_current_key_idx + 1}")
    return True
