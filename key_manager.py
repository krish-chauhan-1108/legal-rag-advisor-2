from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Load all available keys
AVAILABLE_KEYS = [k for k in [
    settings.gemini_api_key,
    settings.gemini_api_key_fallback,
    settings.gemini_api_key_3,
    settings.gemini_api_key_4
] if k and k.strip()]

_current_key_idx = 0

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
