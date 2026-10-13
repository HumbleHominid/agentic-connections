from __future__ import annotations

import functools
import tomllib
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]  # src/connections_redteam/utils.py


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root() / path


def _namespace(d: dict) -> SimpleNamespace:
    """Nested dicts (incl. TOML inline tables) -> attribute access (``cfg.paths.runs.main``)."""
    return SimpleNamespace(
        **{k: _namespace(v) if isinstance(v, dict) else v for k, v in d.items()}
    )


@functools.cache
def _read_config() -> SimpleNamespace:
    with open(repo_root() / "configs" / "config.toml", "rb") as f:
        return _namespace(tomllib.load(f))


def load_config(force_recompute: bool = False) -> SimpleNamespace:
    """Load ``configs/config.toml`` once; ``force_recompute`` re-reads it from disk."""
    if force_recompute:
        _read_config.cache_clear()
    return _read_config()


def cached[T](
    node: str | Path,
    compute: Callable[[], T],
    load: Callable[[Path], T],
    save: Callable[[T, Path], None],
    *,
    force: bool = False,
) -> T:
    """Load ``node`` if it exists, else compute it, save it, return it."""
    path = resolve_path(node)
    if path.exists() and not force:
        return load(path)
    obj = compute()
    path.parent.mkdir(parents=True, exist_ok=True)
    save(obj, path)
    return obj
