# Reckon

[![tests](https://github.com/jhdgeai/reckon/actions/workflows/tests.yml/badge.svg)](https://github.com/jhdgeai/reckon/actions/workflows/tests.yml)

**Reckon creates a log of all the work you do in Claude Code (the AI coding assistant) and estimates
its token cost before it starts.**

Built during August and September 2026. I use this build myself, and I am publishing this redacted
core for others to review and try out. I may or may not come back to update or maintain it, but this
snapshot is out there.

## Quickstart

On macOS, in Terminal. Run `python3 --version` first: Reckon needs Python 3.9 or later, and
[QUICKSTART.md](docs/QUICKSTART.md) says where `python3` and `git` come from on macOS and what the
install was tested on.

```sh
git clone https://github.com/jhdgeai/reckon.git
cd reckon
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

That downloads Reckon, makes a Python environment for it inside the folder, and installs the one
command, `reckon`, over `estimate`, `gate`, `record`, `report`, `usage` and `status`. The pip upgrade line is needed on
the Python 3.9 that comes with macOS, whose pip is too old to install a folder like this one.
Until the environment is active macOS has `python3` and `pip3` but no `python` or `pip`; inside it,
both work. In a new Terminal window, run `source .venv/bin/activate` from the `reckon` folder again
first.

See [QUICKSTART.md](docs/QUICKSTART.md) for every command's actual captured output, run end to end
on this repository's own sample, and how to go on to your own work.

## Why

AI coding and other generative AI tasks are notoriously difficult to size before they start, and
they can be costly to complete. Reckon answers three questions that Claude Code's own interface does
not:

1. **Should this piece of work start at all, at this size?** A task is priced before it runs, and
   a gate allows it, asks first, or blocks it.
2. **What did that session cost?** The Recorder reads the session's own transcript and prices every
   message at list rates. It is an estimate at list prices, not a bill.
3. **Were the estimates any good?** Every estimate is logged beside its actual, and the estimator
   is tested against that history.

It also supports compliance and risk management. Organisations deploying AI tools need to capture
their AI use cases, and Reckon records each piece of work as it happens: what it was for, what data
it touched, whether it is an AI system and in what role, who approved it, and what it cost.

## What this is not

- **Not an audited compliance tool.** It supports the record-keeping compliance work needs; nothing
  here has been reviewed or certified against a compliance framework.
- **Not a bill.** Every figure is a client-side estimate at list rates, from the transcript's own
  token counts. What an account is actually charged can differ, and Claude on the web, the desktop
  app or a phone leaves no transcript on this computer, so it is not counted.
- **Not maintained on a schedule.** It is a snapshot, published as-is; it may or may not be updated.
- **Not a general cost tracker.** Claude Code sessions only, read from local transcripts on this
  computer -- nothing else, and no other tool.
- **The cost gate stands in front of scripted tasks only.** It does not stop or price a conversation
  as you type in it.
- **The estimator's ranges are wide.** The top of a typical range was about ten times the bottom, so
  its predictions are not yet ready to rely on.
- **The estimator and the gate still infer headroom** from the points where requests were refused.
  From 1.2.0 `reckon usage` and `reckon status` show the account's own usage meter, but they read
  the copy the Claude desktop app keeps on this machine, not the account itself, and the gate does not
  use it.
- **Not isolated from the network, in use.** Reckon itself makes no network calls: no telemetry, no
  uploads, no account, nothing is sent anywhere by this code. It is normally driven through Claude
  Code, which is a remote service. A session that reads your records in order to update them puts
  their contents into that session's context, and a record it edits travels both ways. The program
  is offline; the way you operate it usually is not.
- **The append-only check is not tamper-proofing.** It holds each file's length and a hash of
  exactly those bytes, and reports a file whose earlier bytes moved. That catches an accidental
  edit, a truncation and a half-written line. It does not defend against anything that can also
  re-take the baseline, including the assistant that writes the records in the first place. It is a
  smoke alarm, not a lock. The independent witness is your version history, because rewriting that
  is forbidden by rule.
- **It does not redact.** See [the data model](docs/DATA-MODEL.md) rule 5 for why that was left out
  rather than half-built. An export states how many identifying values it carries, and writing one
  needs a recorded consent.

## What is in this package

| Folder | What it does |
|---|---|
| `reckon/` | The one command, over the four modules below: `reckon estimate`, `reckon gate`, `reckon record`, `reckon report`, and from 1.2.0 `reckon usage` and `reckon status`, the account's own usage meter. Each subcommand calls the existing module's own function; no logic is copied into it. |
| `store/` | The data model. Projects, Tasks, Runs and Decisions are kept as plain Markdown and JSON files, with no database. Each record gets a permanent reference, and the append-only logs are checked for edits. It also classifies each project -- what tier it sits in, whether it is an AI system, what role you hold, and whether its output reaches a third party -- and requires a recorded consent before an export is written. |
| `wrapper/` | The cost gate and the launcher. Before a scripted task runs, the gate prices its brief against past costs for that kind of task and answers allow, ask or block. The launcher builds the one command that runs the task. |
| `estimator/` | Predicts the size of a piece of work before it starts. It reads the proposal, predicts how many assistant messages the work will take, turns that into a cost range using past sessions, and reports how often its past ranges contained the real figure. `model.json` holds the fitted numbers. |
| `ledger/` | Measures what sessions cost. It reads Claude Code's local transcripts, prices each message's tokens at published list rates from `prices.json`, turns one session into a Run record, and estimates how close usage is to the five-hour and weekly limits. It also reads the usage meter the Claude desktop app keeps, a pasted copy of the usage page, and the reading Claude Code gives a status line, and warns at 80 per cent of a limit. |
| `sample/` | A small sample of real records, redacted: every person reads `[Approver]` and free text is replaced. `tasks/` holds copies of three of those sample tasks with their state changed to `approved`, so the gate table below is the real gate's own answer rather than a rule about the shipped, unapproved originals. `session/` holds one invented Claude Code session, marked as such, so `reckon record` has something to run on a fresh install. `SAMPLE.md` shows the estimator and the gate working on all of it. |
| `docs/` | The quickstart, getting started and settings, the data model, and the method. |
| `writing/` | A sample of findings to date. |

## `reckon estimate` and `reckon gate`

```
$ reckon estimate "Add a --json flag to an existing CLI subcommand, with a test."
PROPOSAL
  Add a --json flag to an existing CLI subcommand, with a test.

BROKEN INTO 2 PIECE(S)
  $  8.14   29.8 turns  Add a --json flag to an existing CLI subcommand
  $  8.14   29.8 turns  with a test

COST, AS A RANGE, NOT A POINT
  low   $    4.89   (24 turns, 1 session(s))
  p50   $   16.28   (57 turns, 1 session(s))
  high  $   52.45   (127 turns, 2 session(s))

HIT RATE OF THIS KIND OF RANGE: 78%
  21 of 27 leave-one-out predictions contained the actual turn count inside the stated range.

  A client-side estimate at list rates and a floor on what the account loses. Not a bill. Not sterling.
```

```
$ reckon gate sample/tasks/P-0001-T08.md
task     P-0001-T08  sample/tasks/P-0001-T08.md
state    approved
estimate $14.00  (source: front_matter) -- est_p95_usd from the task file's front matter
gate     ASK against $10.00 in gate.json
         - estimated p95 $14.00 is above the $10.00 threshold in gate.json (est_p95_usd from the task file's front matter).
rail     subscription
command  <claude> -p "$(cat sample/tasks/P-0001-T08.md)" --allowedTools Read,Edit,Write,Bash --permission-mode acceptEdits --output-format json --session-id <session id>

ASK. Nothing was run. Answer the points above, then re-run with --execute once they are settled.
```

`<claude>` is where Claude Code is installed on your computer and `<session id>` is new on every
run. Without Claude Code the `command` line reads `shape` instead, with a note that it was not
checked. `reckon record` and `reckon report`, the other two `reckon gate` answers and the form
without Claude Code are captured in full in [QUICKSTART.md](docs/QUICKSTART.md).

## Where it could go next

- **The work-breakdown rule is a punctuation split, not a reading of the proposal** — see
  [The method](docs/METHOD.md) §5 for exactly how it works today. Understanding what a proposal is
  actually asking for, rather than splitting on commas and dashes, is a current area of focus.
- Give the estimator a breakdown of each piece of work to size, instead of a one-line title.
- Put the gate in front of conversational sessions, not only scripted tasks.
- Count work done outside Claude Code.

## Tests

Python 3.9 or later, standard library only, no network access. Inside the environment from the
Quickstart, from the top of the repository:

```sh
python -m unittest discover -s store/tests
python -m unittest discover -s wrapper/tests
python -m unittest discover -s estimator/tests
python -m unittest discover -s ledger/tests
python -m unittest discover -s reckon/tests
```

https://github.com/jhdgeai/reckon/actions runs the same five suites on every push -- that is the badge at the top of
this page.

These are the tests the authors used while building Reckon. They are by no means exhaustive, and
your own use may need more; your mileage may vary.

## Read these

- [Quickstart](docs/QUICKSTART.md) — install, then every command, with its actual captured output.
- [Getting started and settings](docs/SETTINGS.md) — every setting, the file it lives in, its value
  and how to change it.
- [The data model](docs/DATA-MODEL.md) — the records, and the rules that help to maintain their
  integrity.
- [The method](docs/METHOD.md) — estimate, gate, measure, compare.
- [The usage meter](docs/USAGE.md) — `reckon usage` and `reckon status`: the account's own five-hour and weekly
  percentages, what it reads, and what it will not do.
- [A sample of findings to date](writing/what-the-register-measured.md)

## Licence

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
