"""Replay state and per-clock snapshots. Pure Python, no Streamlit imports.

The UI keeps one ReplayState in session state and asks Replay for a snapshot at the
current clock. Snapshots depend only on (dataset, config, clock), so they are cached.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .metrics import compute_metrics, event_time
from .validator import validate_config


# Known paused timestamps per dataset (label, seconds). The demo match has no genuine
# comeback (no side overturns a deficit), so the third moment is "Late pressure".
DEMO_MOMENTS = {
    "MP-DEMO-001": (
        ("Momentum swing", 1000),  # 16:40 swing towards Harbor City while Northbridge FC control the half
        ("Goal moment", 5060),     # 84:20 Northbridge FC late winner
        ("Late pressure", 4650),   # 77:30 Northbridge FC pushing at 1-1
    ),
}


def clock_label(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


@dataclass
class ReplayState:
    """Transient playback state: where the clock is and whether it is running."""
    duration: int
    clock: int = 0
    playing: bool = False

    def play(self) -> None:
        if self.clock < self.duration:
            self.playing = True

    def pause(self) -> None:
        self.playing = False

    def reset(self) -> None:
        self.clock = 0
        self.playing = False

    def seek(self, seconds: int) -> None:
        self.clock = max(0, min(int(seconds), self.duration))
        if self.clock >= self.duration:
            self.playing = False

    def jump_to(self, seconds: int) -> None:
        """Move to a timestamp and pause there (demo moments)."""
        self.seek(seconds)
        self.playing = False

    def tick(self, step: int) -> None:
        """Advance a fixed number of simulated seconds; stop at full time."""
        if self.playing:
            self.seek(self.clock + step)


class Replay:
    """Read-only view of one validated match + config, with cached snapshots per clock."""

    def __init__(self, match: dict, config: dict):
        errors = validate_config(config)
        if errors:
            raise ValueError("; ".join(errors))
        self.match = match
        self.config = config
        self.duration = match["duration_minutes"] * 60
        self.players = {p["id"]: p for t in (match["home_team"], match["away_team"]) for p in t["players"]}
        self.snapshot = lru_cache(maxsize=None)(self._snapshot)

    def new_state(self) -> ReplayState:
        return ReplayState(duration=self.duration)

    def _snapshot(self, at: int) -> dict:
        result = compute_metrics(self.match, self.config, at)
        events = [ev for ev in self.match["events"] if event_time(ev) <= at]
        return {
            "at_seconds": at,
            "clock": clock_label(at),
            "period": events[-1]["period"] if events else 1,
            "events": events,
            "metrics": result["metrics"],
        }
