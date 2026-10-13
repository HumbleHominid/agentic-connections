from __future__ import annotations

import json
import random
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from connections_redteam.utils import cached, load_config

URL = "https://www.nytimes.com/svc/connections/v2/{date}.json"
USER_AGENT = "connections-redteam research script"


@dataclass(frozen=True)
class Puzzle:
    date: str
    id: int
    groups: tuple[tuple[str, tuple[str, ...]], ...]  # (title, 4 words), in source order


def _download(day: str) -> dict:
    req = urllib.request.Request(URL.format(date=day), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _download_valid(day: str) -> dict:
    raw = _download(day)
    if raw.get("status") != "OK":
        raise ValueError(f"puzzle {day}: status {raw.get('status')!r}")
    parse(raw)  # only valid puzzles reach the cache
    return raw


def fetch(day: str, *, force: bool = False) -> dict:
    """Raw puzzle JSON for ``day`` (YYYY-MM-DD), cached at ``<paths.puzzles>/<day>.json``."""
    return cached(
        Path(load_config().paths.puzzles) / f"{day}.json",
        lambda: _download_valid(day),
        lambda p: json.loads(p.read_text()),
        lambda obj, p: p.write_text(json.dumps(obj)),
        force=force,
    )


def parse(raw: dict) -> Puzzle:
    groups = tuple(
        (c["title"], tuple(card["content"] for card in c["cards"])) for c in raw["categories"]
    )
    if len(groups) != 4 or any(len(words) != 4 for _, words in groups):
        raise ValueError(f"puzzle {raw.get('print_date')} is not 4 groups of 4")
    if len({w.strip().upper() for _, ws in groups for w in ws}) != 16:
        raise ValueError(f"puzzle {raw.get('print_date')} has repeated words")
    return Puzzle(date=raw["print_date"], id=raw["id"], groups=groups)


def load_range() -> list[Puzzle]:
    """Every puzzle in ``[game.date_start, game.date_end]``.

    Any fetch or parse failure raises: a silently smaller pool would let the same
    seed select different puzzles on a re-run.
    """
    cfg = load_config()
    day, end = date.fromisoformat(cfg.game.date_start), date.fromisoformat(cfg.game.date_end)
    puzzles = []
    while day <= end:
        puzzles.append(parse(fetch(day.isoformat())))
        day += timedelta(days=1)
    return sorted(puzzles, key=lambda p: p.date)


def select(puzzles: list[Puzzle], seed: int, n: int) -> list[Puzzle]:
    if n > len(puzzles):
        raise ValueError(f"cannot select {n} puzzles from a pool of {len(puzzles)}")
    return random.Random(seed).sample(puzzles, n)
