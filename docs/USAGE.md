# The usage meter: `reckon usage` and `reckon status`

New in 1.2.0. **This is an addition to Reckon, not the reason it exists.** Reckon is for sizing and
gating a piece of work before it starts, for what each session cost, for whether the estimates were
any good, and for a record of each piece of work. `reckon usage` adds the one thing the rest cannot
see: **the account's own usage meter**, the five-hour and weekly percentages that Claude shows you.

Every other figure in Reckon comes from Claude Code's transcripts, so it covers Claude Code only.
Use in the desktop app's chat, on the web or on a phone uses the same limits and leaves no
transcript. The meter is where that use shows up.

## What it reads

**1. The desktop app's own file.** The Claude desktop app for Mac keeps a history of the meter at

```
~/Library/Application Support/Claude/plan-usage-history.json
```

`reckon usage` opens it read-only. Four things to know about that file:

- **The format is undocumented.** It is read as found on 16 September 2026 (format version 2). A
  later app may change it; Reckon then reports what it could not read and leaves it out.
- **The app writes to it only while the app is running**, about every fifteen minutes. A closed
  laptop and a quiet afternoon look the same, so every reading is shown with its gaps and with how
  much of its own time span it covers.
- **It keeps about thirty days** and drops a day off the back each day. `reckon usage --archive`
  copies the samples into an archive of Reckon's own, so they outlast the app's copy. Nothing runs
  that on a schedule unless you set one up.
- **It has no reset times** and no split by product. For those, use the paste below.

**2. A paste of the usage page.** In Claude, open Settings, then Usage. Select the whole panel,
copy it, and save it as a text file. Then:

```
$ reckon usage --paste --file panel.txt --taken-at 2026-09-16T05:20:00Z
```

Paste the whole panel, not one figure at a time: Reckon picks out what it knows and keeps every
line it did not recognise, so a new row on the page shows up instead of vanishing. The page gives
clock times with no date, so `--taken-at` says when you read it. Reckon shows what it read and
waits for a yes before it saves anything; `--yes` saves without asking.

## What it shows

From the desktop file, one block per account. Captured on the owner's Mac on 16 September 2026;
the folders shown differ per computer, and parts are cut where marked `...`:

```
$ reckon usage
2,593 sample(s) across 2 account(s).
  read 1,505 from ~/Library/Application Support/Claude/plan-usage-history.json
  absent, and that is not an error: ~/Library/Application Support/claude-ledger/plan-usage/plan-usage-history.json
  ...

account-2
  newest reading 2026-09-16T20:28:53.510000Z (0.1h old): five-hour 6%, seven-day 45%
  142 samples, 2026-09-15T08:48:41.057000Z to 2026-09-16T20:28:53.510000Z
  1 gap(s) over 60 minutes; 0 over 3 hours; longest 1.5h
  covers 95.7% of its own span -- the rest is hours this file says nothing about
  ...
```

From a paste:

```
Read from the paste:
  plan: Pro
  session (five-hour): 9%, resets 11:00 AM
  week (seven-day):    22%, resets Saturday 8:00 AM
  usage credits, as the page wrote it: $0
  this week by product: Claude Code 98%, Chats 0%, Cowork 2%, Other 0%
  forecast: On track. You should reach Saturday's reset with room to spare.
  last updated: just now
  taken at: 2026-09-16T05:20:00Z
  account: not stated by the page
```

`--json` gives either one in a form a program can read.

## Where the limits stand now: `reckon status`

New in 1.2.1. One answer to "how much of each limit is left", from every source that has a reading:
the desktop file, saved pastes, and the status line below. Each figure names its source, its age
and its reset time where that source has one. Captured on the owner's Mac on 17 September 2026:

```
$ reckon status
Five-hour limit
   20%  desktop app's file, account-2: taken 2026-09-17 08:58 UTC, 6 min ago, reset time not in this source
Seven-day limit
   49%  desktop app's file, account-2: taken 2026-09-17 08:58 UTC, 6 min ago, reset time not in this source

Cross-check: 4% of the observed seven-day ceiling, from 7 refusal(s), computed 2026-09-17T09:03 -- ...
```

- **Where two sources disagree, both are shown.** Nothing is averaged.
- **A reading older than its own window is named and not shown as a percentage**: a five-hour
  figure more than five hours old, a weekly one more than seven days old, or one whose reset time
  has passed. It describes a window that has ended.
- **The split by product** is shown when a paste from the last seven days has one.
- **The cross-check underneath** is Reckon's older estimate, from the points where requests were
  refused. It is kept to show when the two disagree; it is a shape, not a gauge.

### The warning at 80 per cent

At 80 per cent of either limit, `reckon status` starts with a line in words:

```
WARNING: the five-hour limit is at 80% (desktop app's file). At the rate of these readings it
reaches 100% on Thursday 17 September at about 14:00 UTC (a straight line through 9 readings
since 2026-09-17 12:00 UTC).
```

The projection is a straight line through one source's readings since the percentage last fell,
for one account. With one reading, or readings that are not rising, it warns without a projection.
**For the weekly limit it gives no projection through a known change to that limit**, and says why:
readings either side of a change are percentages of two different limits. The one change Reckon
knows is the end of 13 September 2026, Pacific time, when the weekly limit changed for every Pro,
Max, Team and seat-based Enterprise plan.

## The status line

**For Claude Code in a terminal.** Claude Code's documentation says it runs a status-line command
after each message and hands it the account's five-hour and weekly percentages with their reset
times, for subscribers, after the first reply. That makes it the one automatic source with reset
times. `ledger/statusline.py` prints one short line for the bar, such as
`5h 20% (resets 15:00) · 7d 49%`, and keeps the reading for `reckon status`. To turn it on, add
this to `~/.claude/settings.json`, with the path to your downloaded folder:

```
"statusLine": {"type": "command",
               "command": "python3 '/path/to/reckon/ledger/statusline.py'"}
```

It writes a reading when the figures change or fifteen minutes have passed, not after every
message. If it cannot read its input it prints a short line and writes nothing. Removing the setting
loses the reset times and nothing else.

**What has been tested, and what has not.** The script is tested against the input that
documentation describes, with reset times given either as a number of seconds or as a date. It has
not yet been seen running in a live terminal session. On 17 September 2026 the Claude desktop app's
Code tab loaded the same setting and did not run the command at all, so **in the desktop app, use
`reckon usage --paste` instead**: copy the usage page and paste it whole. It gives the same two
percentages and reset times, when you choose to take them.

## In the report

`reckon report` ends with the last seven days: Claude Code's measured cost beside the meter for the
same days, per source and account, with how much of the period the desktop file covers. Reckon sees
Claude Code only, and chat in the app, on the web and on a phone uses the same limits, so the
measured cost is a floor and the meter is the whole account.

## What it will not do

- **It does not turn a percentage into money.** The meter is not a bill, and it is not Reckon's
  cost estimate. The desktop file carries one further figure on some samples; it states no unit and
  it has gone down between samples, so Reckon shows it without a currency.
- **It does not write account identifiers down.** Each account is labelled `account-1`,
  `account-2` in order of first appearance, by the same rule `reckon record` uses. The identifiers
  are hashed on the way in and do not appear in the output, the archive or the saved pastes.
- **It does not join weekly percentages across 13 September 2026.** The weekly limit changed that
  day, so a seven-day percentage from before it and one from after are two scales, and the output
  says so.
- **It makes no network calls.** Every source is a file already on your computer.

## Where it writes

| What | Where | When |
|---|---|---|
| The archive of the desktop file | `~/Library/Application Support/claude-ledger/plan-usage/` | Only with `--archive`. Outside the downloaded folder, so it is not in `git status` |
| Saved pastes | `ledger/plan-usage-observations.jsonl` in the downloaded folder, or `--observations` | Only after a yes, or with `--yes`. Appended to, one line per paste; a later paste does not replace an earlier one |
| Status-line readings | `ledger/plan-usage-statusline.jsonl` in the downloaded folder | Only once the status line is turned on. Appended to |
| Hand-taken copies of the desktop file | `ledger/plan-usage/`, if you make one | Read, not written |

The last three are listed in `.gitignore`. `reckon status` and `reckon report` write nothing.
