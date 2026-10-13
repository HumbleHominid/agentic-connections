from __future__ import annotations

import json
import random
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from connections_redteam.utils import cached, load_config

URL = "https://www.nytimes.com/svc/connections/v2/{date}.json"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


@dataclass(frozen=True)
class Puzzle:
    date: str
    id: int
    groups: tuple[tuple[str, tuple[str, ...]], ...]  # (title, 4 words), in source order


def _download(day: str) -> dict:
    req = urllib.request.Request(URL.format(date=day), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch(day: str, *, force: bool = False) -> dict:
    """Raw puzzle JSON for ``day`` (YYYY-MM-DD), cached at ``<paths.puzzles>/<day>.json``."""
    return cached(
        Path(load_config().paths.puzzles) / f"{day}.json",
        lambda: _download(day),
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
    return Puzzle(date=raw["print_date"], id=raw["id"], groups=groups)


def load_range() -> list[Puzzle]:
    """Every puzzle in ``[game.date_start, game.date_end]``; failures are logged and skipped."""
    cfg = load_config()
    day, end = date.fromisoformat(cfg.game.date_start), date.fromisoformat(cfg.game.date_end)
    puzzles = []
    while day <= end:
        try:
            puzzles.append(parse(fetch(day.isoformat())))
        except Exception as e:
            print(f"skip {day}: {e}", file=sys.stderr)
        day += timedelta(days=1)
    return sorted(puzzles, key=lambda p: p.date)


def select(puzzles: list[Puzzle], seed: int, n: int) -> list[Puzzle]:
    return random.Random(seed).sample(puzzles, n)
