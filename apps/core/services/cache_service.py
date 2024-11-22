# apps/core/services/cache_service.py

from django.core.cache import cache
from typing import Optional, Any
import json
import logging

logger = logging.getLogger(__name__)
class CacheService:
    @staticmethod
    async def get_or_set(key: str, callback, timeout: int = 3600) -> Any:
        """Get from cache or set if missing"""
        try:
            result = cache.get(key)
            if result is None:
                result = await callback()
                if result is not None:
                    cache.set(key, json.dumps(result), timeout=timeout)
                return result
            return json.loads(result)
        except Exception as e:
            logger.warning(f"Cache operation failed: {str(e)}")
            return await callback()