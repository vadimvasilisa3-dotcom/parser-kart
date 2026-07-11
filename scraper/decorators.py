import logging
import sys
from functools import wraps
from typing import Callable, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("YandexMapsScraper")

def log_execution(func: Callable) -> Callable:
    """
    Decorator to log the start and end of a function execution.
    Useful for tracing the flow of the scraper.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.debug(f"▶️ Starting: {func_name}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"✅ Completed: {func_name}")
            return result
        except Exception as e:
            logger.error(f"❌ Error in {func_name}: {e}")
            raise
    return wrapper

def handle_errors(default_return: Any = None, raise_error: bool = False) -> Callable:
    """
    Decorator to handle exceptions gracefully.
    
    Args:
        default_return: Value to return if an exception occurs (if not raising).
        raise_error: Whether to re-raise the exception after logging.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"⚠️ Handled error in {func.__name__}: {str(e)}")
                if raise_error:
                    raise
                return default_return
        return wrapper
    return decorator


