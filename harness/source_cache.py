"""Trusted same-directory atomic Triton cache writes for Landlock ABI 1."""

import os
from pathlib import Path
import tempfile


def atomic_put(manager, data, filename, binary=True):
    if not manager.cache_dir or not manager.lock_path:
        raise RuntimeError('concrete cache directory required')
    if not isinstance(filename, str) or Path(filename).name != filename or filename in ('', '.', '..'):
        raise ValueError('single cache filename required')
    payload = data if isinstance(data, bytes) else str(data)
    descriptor, temporary = tempfile.mkstemp(prefix='.atomic-', dir=manager.cache_dir)
    destination = manager._make_path(filename)
    try:
        with os.fdopen(descriptor, 'wb' if isinstance(payload, bytes) else 'w') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return destination


def __getattr__(name):
    if name != 'SourceCacheManager':
        raise AttributeError(name)
    from triton.runtime.cache import FileCacheManager
    class SourceCacheManager(FileCacheManager):
        put = atomic_put
    return SourceCacheManager
