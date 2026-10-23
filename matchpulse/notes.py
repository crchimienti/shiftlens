"""Analyst notes: free text attached to an exact match-clock second. Session-only by design.

Notes live in the Streamlit session (server memory for this browser tab) and can be exported / imported as
JSON so they survive a reload without any server-side storage. They are user text: they are escaped when shown
and never enter the explanation request, the metrics or the validator.
"""
from __future__ import annotations

import json

from .replay import clock_label

FORMAT = "shiftlens-notes/1"
MAX_NOTES = 200
MAX_TEXT = 500


def make_note(seq: int, seconds: int, text: str, lens: str, move_id: str | None) -> dict:
    return {"id": seq, "seconds": int(seconds), "clock": clock_label(int(seconds)), "text": text.strip()[:MAX_TEXT],
            "lens": lens, "move_id": move_id}


def ordered(notes: list[dict]) -> list[dict]:
    """By match time, then in the order they were written."""
    return sorted(notes, key=lambda n: (n["seconds"], n["id"]))


def to_json(notes: list[dict], match_id: str) -> str:
    keep = ("seconds", "clock", "text", "lens", "move_id")
    return json.dumps({"format": FORMAT, "match_id": match_id,
                       "notes": [{k: n[k] for k in keep} for n in ordered(notes)]}, indent=2, ensure_ascii=False)


def to_markdown(notes: list[dict], title: str) -> str:
    lines = [f"# Analyst notes · {title}", ""]
    lines += [f"- **Min {n['clock']}**" + (f" (move {n['move_id']})" if n["move_id"] else "") + f": {n['text']}"
              for n in ordered(notes)]
    return "\n".join(lines) + "\n"


def parse_import(raw: bytes | str, match_id: str, duration: int, next_seq: int) -> tuple[list[dict], list[str]]:
    """Notes from an exported file. Rejects other formats, other matches and out-of-range times; never raises."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return [], ["Not a JSON file."]
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return [], [f"Not a ShiftLens notes file (expected format '{FORMAT}')."]
    if data.get("match_id") != match_id:
        return [], [f"These notes belong to another match ({data.get('match_id')!r})."]
    out, errors = [], []
    for i, n in enumerate(data.get("notes") or []):
        seconds, text = (n.get("seconds"), n.get("text")) if isinstance(n, dict) else (None, None)
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not 0 <= seconds <= duration:
            errors.append(f"Note {i + 1}: time outside the match.")
        elif not isinstance(text, str) or not text.strip():
            errors.append(f"Note {i + 1}: empty text.")
        else:
            move = n.get("move_id") if isinstance(n.get("move_id"), str) else None
            out.append(make_note(next_seq + len(out), seconds, text, str(n.get("lens") or "analyst"), move))
    return out[:MAX_NOTES], errors


def merge(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Add incoming notes, skipping exact duplicates (same second and text), capped at MAX_NOTES."""
    seen = {(n["seconds"], n["text"]) for n in existing}
    fresh = [n for n in incoming if (n["seconds"], n["text"]) not in seen]
    return (existing + fresh)[:MAX_NOTES]
