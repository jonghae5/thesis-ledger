import json
import os
import time
from pathlib import Path
from typing import Callable

CACHE_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw_cache"


def cached_fetch(provider: str, key: str, ttl_seconds: int, fetch_fn: Callable[[], dict]) -> dict:
    path = CACHE_ROOT / provider / f"{key}.json"
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < ttl_seconds:
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                # Treat a partial/corrupt cache write as a miss. The source is
                # safer than propagating malformed cached market data.
                pass
    data = fetch_fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(data))
    os.replace(temp_path, path)
    return data
