# SPDX-License-Identifier: Apache-2.0
"""Session records: which task a session did, how long it was active, how it ended.

spec-core.md item 3 (§3.2 to §3.6), carried into Reckon 1.2.0 as R7 of
package/RECKON-1.2-SPEC.md. Every function here reads the transcript records
the Recorder already holds, plus two record files: the Board's decisions and
the gate settings. Nothing is typed by a person and nothing is guessed.

THE ONE EXCEPTION TO "NEVER READ PROMPT TEXT" (§3.3, decided by the owner on
13 September 2026: "A with B as confirmation / backup"). The Recorder may read
exactly one line, `register-task: P-NNNN-TNN`, and only from the session's first
typed message. Nothing else in any prompt is read, and a marker anywhere else --
a later message, a quotation mid-line, inside a system reminder -- is ignored.

No third-party dependencies, no network. The transcript tree is read-only.
"""

import re
from datetime import datetime

MARKER = re.compile(r"^register-task: (P-\d{4}-T\d+)[ \t]*$", re.MULTILINE)
CEILING_MARKER = re.compile(r"^register-ended: ceiling[ \t]*$", re.MULTILINE)
SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
INTERRUPT = "[Request interrupted by user"
OUTCOME_COMMAND = re.compile(r"--outcome\b|\bappend_outcome\(")

BOARD_START_WINDOW_SECONDS = 120
DEFAULT_IDLE_GAP_MINUTES = 10

ENDINGS = ("finished", "stopped_at_ceiling", "stopped_by_owner", "failed", "unknown")
CENSORING_ENDINGS = ("stopped_at_ceiling", "stopped_by_owner")


def _parse(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _text_blocks(record):
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block.get("text", "") for block in content
                         if isinstance(block, dict) and block.get("type") == "text")
    return ""


def _is_tool_result(record):
    content = (record.get("message") or {}).get("content")
    if record.get("toolUseResult") is not None:
        return True
    return (isinstance(content, list) and bool(content)
            and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content))


def first_typed_message(records):
    """The first user message that is not a tool result or meta, with system
    reminders removed. None when the session has none."""
    for record in sorted((r for r in records if r.get("timestamp")),
                         key=lambda r: r["timestamp"]):
        if record.get("type") != "user" or record.get("isMeta") or _is_tool_result(record):
            continue
        text = SYSTEM_REMINDER.sub("", _text_blocks(record)).strip()
        if text:
            return text
    return None


def marker_task(records):
    """The task named by the marker line in the first typed message, or None."""
    text = first_typed_message(records)
    found = sorted(set(MARKER.findall(text or "")))
    if len(found) == 1:
        return found[0], "marker line in the first typed message"
    if len(found) > 1:
        return None, (f"the first typed message carries {len(found)} different marker "
                      f"lines ({', '.join(found)}), so it names no one task")
    return None, None


def board_start_task(started_at, decisions, window=BOARD_START_WINDOW_SECONDS):
    """§3.3 B: a SessionStarted from the Board in the two minutes before the
    transcript began. Two candidates is ambiguous and links nothing.

    Returns (task_ref, board_started_at, basis)."""
    if not started_at:
        return None, None, None
    begun = _parse(started_at)
    hits = []
    for record in decisions:
        if record.get("kind") != "SessionStarted" or not record.get("at"):
            continue
        lead = (begun - _parse(record["at"])).total_seconds()
        if 0 <= lead <= window:
            hits.append(record)
    if len(hits) == 1:
        return hits[0].get("task_ref"), hits[0]["at"], (
            f"started from the Board at {hits[0]['at']}, "
            f"{int((begun - _parse(hits[0]['at'])).total_seconds())}s before the transcript began")
    if len(hits) > 1:
        return None, None, (f"{len(hits)} Board starts fall in the {window}s before this "
                            f"transcript began, so none of them is taken")
    return None, None, None


def link_task(records, started_at, decisions, hand_link=None):
    """(task_ref, method, detail) per §3.3.

    Marker and Board start agree: `marker`. Only the Board start: `board_start`.
    They disagree: `conflict`, task_ref null, both kept -- neither wins. Neither:
    the hand-written link if there is one (`hand`), else null. A hand link that
    disagrees with an automatic one is a conflict too.
    """
    marker, marker_basis = marker_task(records)
    board, board_at, board_basis = board_start_task(started_at, decisions)
    hand = (hand_link or {}).get("task_ref")
    detail = {"task_ref_marker": marker, "task_ref_board_start": board,
              "task_ref_hand": hand, "board_started_at": board_at}
    notes = [n for n in (marker_basis, board_basis) if n]

    if marker and board and marker != board:
        return None, "conflict", detail, notes + [
            f"the marker names {marker} and the Board start names {board}; neither wins"]
    automatic = marker or board
    method = "marker" if marker else ("board_start" if board else None)
    if automatic and board and marker:
        notes.append("the Board start confirms the marker")
    if automatic and hand and hand != automatic:
        return None, "conflict", detail, notes + [
            f"the {method} names {automatic} and the hand-written link names {hand}; neither wins"]
    if automatic:
        return automatic, method, detail, notes
    if hand:
        return hand, "hand", detail, notes + ["hand-written link in ledger/run-tasks.json"]
    return None, None, detail, notes + [
        "no record links this session to a task: no marker line, no Board start, "
        "no hand-written link"]


def minutes(records, idle_gap_minutes=DEFAULT_IDLE_GAP_MINUTES):
    """(active_minutes, wall_minutes). Active time sums the gaps between
    consecutive timestamps, counting a gap only when it is under the idle
    threshold, so a session left open over lunch is not an hour of work."""
    stamps = sorted(_parse(t) for t in (r.get("timestamp") for r in records) if t)
    if not stamps:
        return None, None
    active = 0.0
    for before, after in zip(stamps, stamps[1:]):
        gap = (after - before).total_seconds() / 60
        if gap < idle_gap_minutes:
            active += gap
    wall = (stamps[-1] - stamps[0]).total_seconds() / 60
    return round(active, 1), round(wall, 1)


def _conversation(records):
    """User and assistant records in time order, without bookkeeping lines."""
    return sorted((r for r in records
                   if r.get("type") in ("user", "assistant") and r.get("timestamp")),
                  key=lambda r: r["timestamp"])


def _recorded_outcome(records):
    for record in records:
        if record.get("type") != "assistant":
            continue
        for block in (record.get("message") or {}).get("content") or []:
            if (isinstance(block, dict) and block.get("type") == "tool_use"
                    and block.get("name") == "Bash"
                    and OUTCOME_COMMAND.search(str((block.get("input") or {}).get("command", "")))):
                return True
    return False


def _ceiling_marker(records):
    return any(record.get("type") == "assistant" and CEILING_MARKER.search(_text_blocks(record))
               for record in records)


def _stood_down(task_ref, board_started_at, decisions):
    """A SessionStoodDown names the Board start it ends, so it can only belong
    to a session matched to that start. A session with no Board start has no
    stand-down to find."""
    if not task_ref or not board_started_at:
        return None
    for record in decisions:
        if (record.get("kind") == "SessionStoodDown" and record.get("task_ref") == task_ref
                and record.get("started_at") == board_started_at):
            return record
    return None


def _failed(conversation):
    if not conversation:
        return None
    last = conversation[-1]
    if last.get("type") == "assistant" and (
            last.get("isApiErrorMessage") or (last.get("message") or {}).get("model") == "<synthetic>"):
        return "the transcript ends on an API error with no later assistant turn"
    if last.get("type") == "user" and _is_tool_result(last):
        content = (last.get("message") or {}).get("content") or []
        if any(isinstance(b, dict) and b.get("is_error") for b in content):
            return "the transcript ends on a tool error with no later assistant turn"
    return None


def ending(records, *, task_ref=None, board_started_at=None, assistant_messages=0,
           decisions=(), ceiling_messages=None):
    """(ended_how, basis) per §3.4. The order below is the rule:

    1. `register-ended: ceiling` in an assistant message -> stopped_at_ceiling.
       Where the message count disagrees, the marker wins and the basis says so.
    2. last turn ended end_turn and the session recorded an outcome -> finished.
    3. the transcript ends on a user interrupt, or the Board stood down this
       session's start -> stopped_by_owner.
    4. the transcript ends on an API or tool error -> failed.
    5. the assistant-message count reached the ceiling in wrapper/gate.json ->
       stopped_at_ceiling (the backup the owner chose).
    6. otherwise unknown -- a real value, not a gap.
    """
    conversation = _conversation(records)
    last_assistant = next((r for r in reversed(conversation) if r.get("type") == "assistant"), None)
    at_count = bool(ceiling_messages) and assistant_messages >= ceiling_messages

    if _ceiling_marker(records):
        basis = "the session wrote register-ended: ceiling"
        if ceiling_messages and not at_count:
            basis += (f"; the message count ({assistant_messages}) is below the ceiling "
                      f"({ceiling_messages}), and the marker wins")
        return "stopped_at_ceiling", basis

    ended_on_end_turn = bool(conversation) and conversation[-1] is last_assistant and (
        (last_assistant.get("message") or {}).get("stop_reason") == "end_turn")
    if ended_on_end_turn and _recorded_outcome(records):
        return "finished", "last assistant turn ended end_turn and the session recorded an outcome"

    if conversation and conversation[-1].get("type") == "user" and \
            _text_blocks(conversation[-1]).startswith(INTERRUPT):
        return "stopped_by_owner", "the transcript ends on a user interrupt"
    stood = _stood_down(task_ref, board_started_at, decisions)
    if stood:
        return "stopped_by_owner", f"the Board stood this session down at {stood['at']}"

    failed = _failed(conversation)
    if failed:
        return "failed", failed

    if at_count:
        return "stopped_at_ceiling", (
            f"no ceiling marker, but {assistant_messages} assistant messages reached the "
            f"ceiling of {ceiling_messages} in wrapper/gate.json and the session did not finish")

    if ended_on_end_turn:
        return "unknown", ("last assistant turn ended end_turn but the session recorded no "
                           "outcome, so finishing its work is not shown")
    return "unknown", "none of the four endings has evidence in the transcript"


def session_record(records, *, started_at, assistant_messages, decisions=(),
                   hand_link=None, idle_gap_minutes=DEFAULT_IDLE_GAP_MINUTES,
                   ceiling_messages=None):
    """The §3.2 fields for one session, as a dict to merge onto its Run."""
    task_ref, method, detail, notes = link_task(records, started_at, decisions, hand_link)
    ended_how, ended_basis = ending(
        records, task_ref=task_ref or detail["task_ref_marker"] or detail["task_ref_board_start"],
        board_started_at=detail["board_started_at"],
        assistant_messages=assistant_messages, decisions=decisions,
        ceiling_messages=ceiling_messages)
    active, wall = minutes(records, idle_gap_minutes)
    return {
        "task_ref": task_ref,
        "task_link_method": method,
        "task_link_detail": detail,
        "task_link_notes": notes,
        "ended_how": ended_how,
        "ended_how_basis": ended_basis,
        "active_minutes": active,
        "wall_minutes": wall,
        "idle_gap_minutes": idle_gap_minutes,
        "censored": ended_how in CENSORING_ENDINGS,
    }


def account_labels(sessions_records):
    """{owner account id: 'account-N'}, numbered by first appearance in time.

    The identifiers are disclosive and never leave this function: a record
    carries the label, not the id (ledger/rails.json _second_account_note)."""
    first = {}
    for records in sessions_records:
        records = list(records)
        # The owner is named on one bookkeeping line with no timestamp of its
        # own (checked 16 September), so the session's first line dates it.
        stamps = sorted(r["timestamp"] for r in records if r.get("timestamp"))
        if not stamps:
            continue
        for owner in {r["ownerAccountUuid"] for r in records if r.get("ownerAccountUuid")}:
            if owner not in first or stamps[0] < first[owner]:
                first[owner] = stamps[0]
    return {owner: f"account-{i + 1}"
            for i, owner in enumerate(sorted(first, key=first.get))}


def account_for(records, labels, started_at, stated=None):
    """(account, basis). `mixed` when one session carries two. Checked against
    the owner's dated statement where one is recorded, and a disagreement is said."""
    found = sorted({labels[r["ownerAccountUuid"]] for r in records
                    if r.get("ownerAccountUuid") in labels})
    if not found:
        return None, "no transcript line names an owner account"
    account = found[0] if len(found) == 1 else "mixed"
    basis = "owner account named on the transcript's own lines"
    rule = (stated or {}).get("cross_check_rule") or {}
    switch, after = rule.get("stated_switch_at"), rule.get("account_after")
    if switch and after and started_at and started_at >= switch and account != after:
        basis += (f"; DISAGREES with the owner's statement of {stated.get('observed_on')} that all "
                  f"Claude Code work from {switch} was on {after} -- see ledger/rails.json "
                  f"_second_account_dated, where neither source is preferred")
    return account, basis
