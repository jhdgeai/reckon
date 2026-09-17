# The data model

Everything is a plain file. No database, no server, no third-party packages. The code is in
`store/store.py`.

## The records

| Record | Where it lives | Shape | Changes by |
|---|---|---|---|
| **Project** | `projects/P-NNNN.md` | Markdown with front matter | Editing, through stage transitions |
| **Task** | `tasks/P-NNNN-TNN.md` | Markdown with front matter | Editing, through task transitions |
| **Run** | `runs/YYYY-MM.jsonl` | One JSON line per session | **Appending only** |
| **Decision** | `decisions/YYYY-MM.jsonl` | One JSON line per decision | **Appending only** |
| **Reference register** | `store/refs.json` | JSON | Allocation only |

**A Project** is a piece of work worth tracking: its one-liner, its stage (for example
`prototype`), what data it touches, whether it is an AI system and in what role, and where its
files live.

**A Task** belongs to a Project: its brief, its state (`drafted`, `approved`, `running`, `built`,
`shipped`), who approved it and when, its cost estimate at the 95th percentile, and the Runs that
did it.

**A Run** is one assistant session: when it started and ended, the model, the billing rail, token
usage by kind, the estimated cost at list rates and how that cost was derived, and the Task it
served.

**A Decision** is anything a person decided that Reckon must be able to show later: a task moving
state, a gate overridden, a session started or stood down, an export consented to.

## The rules that help to maintain integrity

1. **A reference is allocated once and not reused.** `P-0001`, `P-0001-T08` and `R-0018` are
   written into the reference register the moment they exist, bound to a natural key. Nothing
   recomputes them.
2. **Corrections are new records, not edits.** Runs and Decisions are append-only. A Run read
   before its transcript was complete is superseded by a later record, and both are kept.
3. **The append-only folders are checked.** `store/integrity.py` holds each file's length and a
   hash of those bytes, and reports a file that was edited, truncated or half-written. It reports
   and does not repair.
4. **Stage gates refuse.** Moving a record forward into a stage it owes fields for is refused, and
   the refusal names every missing field. An override needs a name and a reason, and is itself a
   Decision.
5. **A value that could identify anyone lives in a named field.** `store.DISCLOSIVE_FIELDS` names
   them, so an export can count what it is about to carry and say so. **Reckon does not redact.**
   The manifest for every export states how many identifying values are in it, and writing one
   needs a name and a reason recorded as a Decision.

   Redaction was deliberately left out of this package rather than half-shipped. Doing it safely
   takes two halves: replace each identifying field, then check the result against a list of the
   client and company names that must not appear. The second half cannot work for anyone but its
   author, because the list is personal and lives outside the repository, and a check with nothing
   to look for finds nothing and reports it exactly as a pass. A redactor with no check behind it
   would produce clean-looking output that nobody had verified, out of a snapshot that is not
   maintained, and that is worse than no redactor at all.

## The sample

`sample/register-sample.json` holds one Project, three Tasks, their Runs and the Decisions about
them, with every identifying value replaced before publication. Free text reads `[P-0001-T08 · brief]` and similar;
the structure, states, dates, token counts and costs are real.
