"""Build the synthetic 90-minute demo match (data/match_demo.json). Deterministic: same seed → same file.

    python tools/build_match.py          # writes data/match_demo.json
    python tools/build_match.py --check  # exit 1 if the committed file differs from a fresh build

Everything here is invented: fictional clubs, fictional players, scripted arc, synthetic coordinates and a
transparent synthetic xG. Coordinates are 0–100 in the acting team's frame (x towards the goal it attacks,
y = 100 on its left touchline); zone and lane are derived from them with the same rules the validator checks.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from matchpulse.validator import lane_of, zone_of  # noqa: E402

OUT = ROOT / "data" / "match_demo.json"
SEED = 20261027
HOME, AWAY = "NBR", "HBC"

SQUADS = {
    HOME: ("Northbridge FC", [
        ("01", "Tomas Reyes", 1, "GK"), ("02", "Liam Okafor", 2, "DF"), ("04", "Jonas Weber", 4, "DF"),
        ("05", "Mateo Silva", 5, "DF"), ("03", "Ethan Brooks", 3, "DF"), ("06", "Kai Nakamura", 6, "MF"),
        ("08", "Lucas Moreau", 8, "MF"), ("10", "Adrian Novak", 10, "MF"), ("07", "Samuel Adeyemi", 7, "FW"),
        ("11", "Diego Varela", 11, "FW"), ("09", "Marcus Lindqvist", 9, "FW"),
        ("12", "Arlo Pettersen", 12, "GK"), ("14", "Noel Garvey", 14, "DF"), ("16", "Ravi Castell", 16, "MF"),
        ("18", "Tobias Lunde", 18, "MF"), ("19", "Elias Moraru", 19, "FW")]),
    AWAY: ("Harbor City", [
        ("01", "Pavel Horvat", 1, "GK"), ("02", "Noah Fischer", 2, "DF"), ("04", "Victor Almeida", 4, "DF"),
        ("05", "Owen Gallagher", 5, "DF"), ("03", "Rafael Costa", 3, "DF"), ("06", "Yusuf Demir", 6, "MF"),
        ("08", "Hugo Laurent", 8, "MF"), ("10", "Enzo Romano", 10, "MF"), ("07", "Felix Brandt", 7, "FW"),
        ("11", "Isaac Mensah", 11, "FW"), ("09", "Daniel Kowalski", 9, "FW"),
        ("13", "Milan Sorensen", 13, "GK"), ("15", "Theo Valdes", 15, "DF"), ("17", "Ilya Brenner", 17, "MF"),
        ("20", "Jamal Osei", 20, "MF"), ("21", "Bruno Lacerda", 21, "FW")]),
}
OUTFIELD = {"DF": ("02", "03", "04", "05"), "MF": ("06", "08", "10"), "FW": ("07", "09", "11")}

# Scripted arc: (from_minute, home share of possessions, attacking intent of the leading side 0..1)
PHASES = ((0, 0.62), (15, 0.58), (28, 0.42), (40, 0.5), (45, 0.36), (66, 0.5), (76, 0.6))
# Scripted goals: (minute, second, team, scorer, setup) — the generator builds the move that ends in each.
GOALS = ((23, 10, HOME, "09", "through_ball"), (38, 5, AWAY, "09", "corner"), (84, 20, HOME, "10", "cutback"))


def xg(x: float, y: float, header: bool = False) -> float:
    """Synthetic shot quality from distance and angle to the goal centre (100, 50). Not a provider model."""
    dist = math.hypot((100 - x) * 1.05, (y - 50) * 0.68)  # approximate metres on a 105 × 68 pitch
    angle = math.atan2(7.32 * (100 - x) * 1.05, ((100 - x) * 1.05) ** 2 + ((y - 50) * 0.68) ** 2 - (7.32 / 2) ** 2)
    v = 1 / (1 + math.exp(-(-1.1 + 1.6 * abs(angle) - 0.09 * dist)))
    return round(max(0.01, min(0.85, v * (0.7 if header else 1.0))), 2)


class Builder:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.events: list[dict] = []
        self.t = 0  # match second (period 2 starts at 45:00)
        self.seq = 0

    def pid(self, team: str, pos: str | None = None, num: str | None = None) -> str:
        return f"{team}-{num or self.rng.choice(OUTFIELD[pos or self.rng.choice(('DF', 'MF', 'MF', 'FW'))])}"

    def add(self, team: str, kind: str, x: float, y: float, player: str | None = None, outcome: str | None = None,
            end: tuple[float, float] | None = None, gap: int = 3, **extra) -> dict:
        self.t += max(1, gap)
        x, y = round(min(max(x, 0.5), 99.5), 1), round(min(max(y, 0.5), 99.5), 1)
        ev = {"event_id": "", "minute": self.t // 60, "second": self.t % 60, "period": 1 if self.t < 2700 else 2,
              "team_id": team, "type": kind, "x": x, "y": y, "zone": zone_of(x, y), "lane": lane_of(y),
              "sequence_id": f"S{self.seq:03d}"}
        if player:
            ev["player_id"] = player
        if outcome:
            ev["outcome"] = outcome
        if end:
            ev["end_x"], ev["end_y"] = round(min(max(end[0], 0.5), 99.5), 1), round(min(max(end[1], 0.5), 99.5), 1)
        ev.update(extra)
        self.events.append(ev)
        return ev

    # --- one possession ---------------------------------------------------------------------------------------
    def possession(self, team: str, intent: float, until: int, length: int = 9, press: float = 0.18) -> None:
        r, opp = self.rng, AWAY if team == HOME else HOME
        self.seq += 1
        x, y = r.uniform(12, 45), r.uniform(15, 85)
        holder = self.pid(team, "DF")
        for _ in range(r.randint(2, length)):
            if self.t >= until - 20:
                return
            if r.random() < press + 0.12 * (x > 60):  # the opponent presses the ball
                self.add(opp, "pressure", 100 - x, 100 - y, self.pid(opp, "MF" if x < 60 else "DF"), gap=r.randint(1, 2))
            nx = min(97, x + r.uniform(4, 16) * (0.6 + intent))
            ny = min(95, max(5, y + r.uniform(-22, 22)))
            if x > 55 and r.random() < 0.12:
                ok = r.random() < 0.55
                self.add(team, "dribble", x, y, holder, "success" if ok else "fail", gap=r.randint(2, 3))
                if not ok:
                    self.turnover(opp, x, y)
                    return
            if r.random() < 0.25:
                self.add(team, "carry", x, y, holder, end=(nx, ny), gap=r.randint(2, 4))
            else:
                ok = r.random() < (0.86 if x < 60 else 0.68)
                nxt = self.pid(team, "FW" if nx > 70 else "MF")
                kind = "cross" if nx > 80 and (ny < 25 or ny > 75) else "pass"
                self.add(team, kind, x, y, holder, "complete" if ok else "incomplete", end=(nx, ny), gap=r.randint(2, 5))
                if not ok:
                    self.turnover(opp, nx, ny)
                    return
                holder = nxt
            x, y = nx, ny
            if x > 80 and r.random() < 0.45:
                self.shot(team, holder, x, y)
                return
        if r.random() < 0.3:
            self.turnover(opp, x, y)

    def turnover(self, opp: str, x: float, y: float) -> None:
        kind = self.rng.choice(("interception", "tackle", "clearance", "interception"))
        out = {"tackle": "won"}.get(kind)
        self.add(opp, kind, 100 - x, 100 - y, self.pid(opp, "DF" if x > 50 else "MF"), out, gap=self.rng.randint(1, 3))

    def shot(self, team: str, shooter: str, x: float, y: float) -> None:
        r, opp = self.rng, AWAY if team == HOME else HOME
        x, y = min(max(x, 72), 97), min(max(y, 18), 82)
        q = xg(x, y)
        outcome = r.choices(("saved", "off_target", "blocked"), (0.35 + q, 0.45, 0.2))[0]
        self.add(team, "shot", x, y, shooter, outcome, end=(100, 50 + r.uniform(-12, 12)), gap=r.randint(2, 4), xg=q)
        if outcome == "saved":
            self.add(opp, "save", 100 - min(x + 15, 99), 100 - y, f"{opp}-01", gap=1)
            if r.random() < 0.35:
                self.add(team, "corner", 99.5, 99 if y > 50 else 1, self.pid(team, "FW"), "complete", gap=r.randint(8, 14))
        elif outcome == "blocked" and r.random() < 0.5:
            self.add(team, "corner", 99.5, 99 if y > 50 else 1, self.pid(team, "FW"), "complete", gap=r.randint(8, 14))

    def goal(self, minute: int, second: int, team: str, scorer: str, setup: str) -> None:
        r = self.rng
        target = minute * 60 + second
        self.t = max(self.t, target - 16)
        self.seq += 1
        if setup == "corner":
            self.add(team, "corner", 99.5, 1, f"{team}-07", "complete", end=(93, 46), gap=1)
            self.add(team, "goal", 93, 47, f"{team}-{scorer}", gap=target - self.t - 1 if target - self.t > 1 else 1,
                     end=(100, 52), xg=xg(93, 47, header=True))
            return
        self.add(team, "pass", 45, 55, f"{team}-06", "complete", end=(62, 48), gap=1)
        self.add(team, "carry", 62, 48, f"{team}-08", end=(70, 40), gap=3)
        if setup == "through_ball":
            self.add(team, "pass", 70, 40, f"{team}-10", "complete", end=(88, 52), gap=3)
            sx, sy = 88, 52
        else:
            self.add(team, "dribble", 74, 30, f"{team}-07", "success", gap=3)
            self.add(team, "cross", 88, 25, f"{team}-07", "complete", end=(89, 47), gap=3)
            sx, sy = 89, 47
        self.add(team, "goal", sx, sy, f"{team}-{scorer}", gap=target - self.t, end=(100, 49), xg=xg(sx, sy))

    def kickoff(self, team: str, at: int) -> None:
        self.t = at - 1
        self.seq += 1
        self.add(team, "kickoff", 50, 50, f"{team}-09", gap=1)

    def build(self) -> list[dict]:
        r = self.rng
        goal_at = {m * 60 + s: (m, s, team, num, setup) for m, s, team, num, setup in GOALS}
        self.kickoff(HOME, 0)
        pending = sorted(goal_at)
        kicked_second = False
        while self.t < 5340:
            if not kicked_second and self.t >= 2690:
                self.kickoff(AWAY, max(2700, self.t + 1))
                kicked_second = True
            nxt_goal = pending[0] if pending else 10 ** 9
            if self.t >= nxt_goal - 60:
                m, s, team, num, setup = goal_at[pending.pop(0)]
                self.goal(m, s, team, num, setup)
                self.kickoff(AWAY if team == HOME else HOME, self.t + 40)
                continue
            minute = self.t / 60
            share = [s for f, s in PHASES if f <= minute][-1]
            team = HOME if r.random() < share else AWAY
            intent = 0.55 + (0.35 if (team == AWAY) == (45 <= minute < 66) else 0) + r.uniform(-0.15, 0.15)
            limit = min(nxt_goal - 60, 2690 if self.t < 2690 else 5390)
            leading = share if team == HOME else 1 - share
            away_press = team == HOME and 45 <= minute < 66  # Harbor City press high after the break
            self.possession(team, intent, limit, length=5 + round(8 * leading), press=0.4 if away_press else 0.16)
            if r.random() < 0.06:
                foul_team = AWAY if team == HOME else HOME
                self.seq += 1
                fx, fy = r.uniform(30, 75), r.uniform(10, 90)
                self.add(foul_team, "foul", fx, fy, self.pid(foul_team), gap=r.randint(2, 6))
                self.add(team, "free_kick", 100 - fx, 100 - fy, self.pid(team, "MF"), "complete", gap=r.randint(15, 30))
            self.t += r.randint(4, 14)  # ball out of play / restart
        for i, ev in enumerate(self.events, 1):
            ev["event_id"] = f"E{i:04d}"
        return self.events


def build(seed: int = SEED) -> dict:
    events = Builder(seed).build()
    teams = {}
    for team, (name, roster) in SQUADS.items():
        teams[team] = {"id": team, "name": name, "players": [
            {"id": f"{team}-{n}", "name": nm, "number": num, "position": pos, "starter": i < 11}
            for i, (n, nm, num, pos) in enumerate(roster)]}
    score = {"home": sum(e["type"] == "goal" and e["team_id"] == HOME for e in events),
             "away": sum(e["type"] == "goal" and e["team_id"] == AWAY for e in events)}
    return {"match_id": "MP-DEMO-001", "schema_version": "1.1.0", "seed": seed,
            "description": ("Synthetic 90-minute match between fictional clubs. Arc: Northbridge control and lead "
                            "(23'), Harbor City equalise from a corner (38') and press high after the break; "
                            "Northbridge's late winner (84')."),
            "duration_minutes": 90, "home_team": teams[HOME], "away_team": teams[AWAY], "final_score": score,
            "events": events}


def dump(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    text = dump(build())
    if "--check" in sys.argv:
        sys.exit(0 if OUT.read_text(encoding="utf-8") == text else 1)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(build()['events'])} events)")
