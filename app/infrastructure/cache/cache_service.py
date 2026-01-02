"""
Cache Service.
Provides a caching layer using diskcache.
"""
import os
import hashlib
import json
from typing import Any, Optional, Union
import diskcache
import redis
from loguru import logger

from app.core.config import get_settings

class CacheService:
    """
    Service for caching data using diskcache.
    Supports persistent caching with TTL.
    """
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize cache service.
        
        Args:
            cache_dir: Directory to store cache files.
        """
        self.settings = get_settings()
        self.cache_dir = cache_dir or self.settings.cache_dir
        
        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Initialize diskcache
        # size_limit is in bytes (default 1GB)
        self.disk_cache = diskcache.Cache(self.cache_dir, size_limit=1024 * 1024 * 1024)
        
        # Initialize Redis
        self.redis_client = None
        try:
            self.redis_client = redis.from_url(self.settings.redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("Connected to Redis cache")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Falling back to DiskCache.")
            self.redis_client = None
            
        logger.info(f"Cache service initialized at {self.cache_dir}")
        
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        try:
            if self.redis_client:
                # Redis
                value = self.redis_client.get(key)
                if value:
                    logger.debug(f"Cache hit (Redis) for key: {key}")
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                return None
            else:
                # DiskCache
                value = self.disk_cache.get(key)
                if value is not None:
                    logger.debug(f"Cache hit (Disk) for key: {key}")
                return value
        except Exception as e:
            logger.error(f"Error retrieving from cache: {e}")
            return None
            
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (must be picklable)
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.redis_client:
                # Redis
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                self.redis_client.set(key, value, ex=int(ttl) if ttl else None)
            else:
                # DiskCache
                self.disk_cache.set(key, value, expire=ttl)
            return True
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
            return False
            
    def generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate a deterministic cache key.
        
        Args:
            prefix: Key prefix (e.g., 'query', 'embedding')
            *args: Positional arguments to include in key
            **kwargs: Keyword arguments to include in key
            
        Returns:
            Hashed cache key string
        """
        data = {
            "args": args,
            "kwargs": kwargs
        }
        # Sort keys to ensure deterministic output
        json_str = json.dumps(data, sort_keys=True, default=str)
        hash_str = hashlib.md5(json_str.encode()).hexdigest()
        return f"{prefix}:{hash_str}"

    def clear(self) -> None:
        """Clear all cache."""
        if self.redis_client:
            self.redis_client.flushdb()
        self.disk_cache.clear()
        
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete keys matching a pattern.
        
        Args:
            pattern: Glob pattern (e.g. "query:*")
            
        Returns:
            Number of keys deleted
        """
        count = 0
        try:
            if self.redis_client:
                # Redis Scan & Delete
                cursor = '0'
                while cursor != 0:
                    cursor, keys = self.redis_client.scan(cursor=cursor, match=pattern, count=100)
                    if keys:
                        self.redis_client.delete(*keys)
                        count += len(keys)
                        logger.info(f"Invalidated {len(keys)} keys matching '{pattern}'")
            else:
                # DiskCache
                # DiskCache doesn't support easy pattern matching without iteration
                # We iterate roughly
                # Note: This might be slow for large caches
                keys_to_delete = []
                for key in self.disk_cache:
                    if pattern.replace('*', '') in key: # Simple substring match for fallback
                         keys_to_delete.append(key)
                
                for k in keys_to_delete:
                    del self.disk_cache[k]
                count = len(keys_to_delete)
                if count > 0:
                    logger.info(f"Invalidated {count} keys from DiskCache")

        except Exception as e:
            logger.error(f"Error clearing pattern {pattern}: {e}")
            
        return count

    def close(self) -> None:
        """Close cache resources."""
        if self.redis_client:
            self.redis_client.close()
        self.disk_cache.close()
