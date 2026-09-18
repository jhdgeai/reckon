#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The reading Claude Code already gives away -- R3 of package/RECKON-1.2-SPEC.md.

Claude Code runs a status-line command after each message and hands it a JSON
object on standard input. For subscribers, after the first reply, that object
carries `rate_limits.five_hour` and `rate_limits.seven_day`, each with
`used_percentage` and `resets_at`. It is the only automatic source found that
gives the percentages and their reset times together.

This command does three things and nothing else:
  1. prints one short line for the status bar,
  2. appends the reading to ledger/plan-usage-statusline.jsonl as an
     observation, when it differs from the last one written or fifteen
     minutes have passed -- so a busy session does not write a line per
     message, and
  3. overwrites ledger/plan-usage-statusline-called.json with when it last
     ran and whether it had a meter, so `reckon status` can say it never ran.

It never fails loudly. A status line that errors shows the error in the bar of
every session, so any problem prints a short line and writes nothing.

Turned on by a `statusLine` entry in Claude Code's settings:
  "statusLine": {"type": "command",
                 "command": "/usr/bin/python3 /path/to/ledger/statusline.py"}
Removing that entry loses the reset times and nothing else (R3's acceptance).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_READINGS = HERE / "plan-usage-statusline.jsonl"
KIND = "StatusLineUsage"
REWRITE_AFTER = timedelta(minutes=15)
FIGURES = {"five_hour": "5h", "seven_day": "7d"}


def _stamp(when):
    return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _when(value):
    """resets_at as documented is a moment; accept epoch seconds or ISO text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return _stamp(datetime.fromtimestamp(seconds, tz=timezone.utc))
    if isinstance(value, str) and value:
        try:
            when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _stamp(when if when.tzinfo else when.replace(tzinfo=timezone.utc))
    return None


def reading(payload, now=None):
    """The status line's input -> an observation, or None where it has no meter."""
    if not isinstance(payload, dict):
        return None
    limits = payload.get("rate_limits")
    if not isinstance(limits, dict):
        return None
    now = now or datetime.now(timezone.utc)
    out = {"kind": KIND, "source": "Claude Code status line", "taken_at": _stamp(now),
           "session_id": payload.get("session_id"),
           # WHOSE METER IT IS. The owner, 17 September 2026, looking at the Board
           # minutes after the first status-line reading was ever written here:
           # "why do we have three accounts showing in the board?" The reading
           # named no account, so the screen honestly showed it as a third,
           # unnamed one beside his two. The status line's own payload does not
           # say, so the account is taken from the sign-in Claude Code is
           # actually using, and keyed the same way the desktop file's samples
           # are -- the identifier goes in and never comes out.
           "account_key": _account_key()}
    found = False
    for figure in FIGURES:
        block = limits.get(figure)
        block = block if isinstance(block, dict) else {}
        percent = block.get("used_percentage")
        if isinstance(percent, (int, float)) and not isinstance(percent, bool):
            out[f"{figure}_percent"] = round(percent, 1)
            found = True
        else:
            out[f"{figure}_percent"] = None
        out[f"{figure}_resets_at"] = _when(block.get("resets_at"))
    return out if found else None


CLI_CONFIG = Path.home() / ".claude.json"
_KEY_PREFIX = b"p2p-register plan-usage account\n"   # plan_usage.py's, exactly
ACCOUNT_KEY_LENGTH = 16


def _account_key(path=None):
    """The account this terminal is signed in as, as a one-way key, or None.

    The same key the desktop file's samples carry (plan_usage.account_key over
    the organisation identifier), so a status-line reading and a desktop sample
    of the same account land in the same column. Deliberately duplicated rather
    than imported: this command must run with nothing importable but the
    standard library, and it must never fail loudly.
    """
    import hashlib
    try:
        account = json.loads(Path(path or CLI_CONFIG).read_text(encoding="utf-8"))
        org = (account.get("oauthAccount") or {}).get("organizationUuid")
    except (OSError, ValueError, AttributeError):
        return None
    if not org:
        return None
    return hashlib.sha256(_KEY_PREFIX + str(org).encode("utf-8")).hexdigest()[:ACCOUNT_KEY_LENGTH]


def _last_line(path):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 4096))
            tail = handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(tail):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def worth_writing(new, last):
    if not last:
        return True
    same = all(new.get(k) == last.get(k) for k in (
        "five_hour_percent", "seven_day_percent", "five_hour_resets_at", "seven_day_resets_at"))
    if not same:
        return True
    try:
        then = datetime.fromisoformat(last["taken_at"].replace("Z", "+00:00"))
        now = datetime.fromisoformat(new["taken_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError):
        return True
    return now - then >= REWRITE_AFTER


def record(observation, path=None):
    path = Path(path) if path else DEFAULT_READINGS
    if not worth_writing(observation, _last_line(path)):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(observation, sort_keys=True) + "\n")
    return True


def called_path(readings_path=None):
    """Where the note of the last call sits: beside the readings, one small file."""
    path = Path(readings_path) if readings_path else DEFAULT_READINGS
    return path.with_name(path.stem + "-called.json")


def note_called(observation, readings_path=None, now=None):
    """Overwrite the one note saying when the status line last ran and whether it
    had a meter, so `reckon status` can tell never-ran from ran-with-no-meter
    (P-0001-T79). Written on every call, including a call with bad input."""
    note = {"called_at": _stamp(now or datetime.now(timezone.utc)),
            "had_meter": bool(observation)}
    path = called_path(readings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(note, sort_keys=True) + "\n", encoding="utf-8")


def read_called(readings_path=None):
    try:
        return json.loads(called_path(readings_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def line(observation):
    if not observation:
        return "usage: no meter yet"
    parts = []
    for figure, short in FIGURES.items():
        percent = observation.get(f"{figure}_percent")
        if percent is None:
            continue
        text = f"{short} {percent:g}%"
        resets = observation.get(f"{figure}_resets_at")
        if resets and figure == "five_hour":
            local = datetime.fromisoformat(resets.replace("Z", "+00:00")).astimezone()
            text += f" (resets {local.strftime('%H:%M')})"
        parts.append(text)
    return " · ".join(parts)


def main(stdin=None, path=None, now=None):
    path = path or os.environ.get("RECKON_STATUSLINE_READINGS")
    observation = None
    try:
        raw = (stdin if stdin is not None else sys.stdin).read()
        payload = json.loads(raw) if raw.strip() else {}
        observation = reading(payload, now)
        if observation:
            record(observation, path)
        print(line(observation))
    except Exception as exc:                               # noqa: BLE001 -- never loud
        print(f"usage: not read ({exc.__class__.__name__})")
    try:
        note_called(observation, path, now)
    except Exception:                                      # noqa: BLE001 -- never loud
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
