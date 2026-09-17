# The usage meter: `reckon usage`

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
- **It makes no network calls.** Both sources are files already on your computer.

## Where it writes

| What | Where | When |
|---|---|---|
| The archive of the desktop file | `~/Library/Application Support/claude-ledger/plan-usage/` | Only with `--archive`. Outside the downloaded folder, so it is not in `git status` |
| Saved pastes | `ledger/plan-usage-observations.jsonl` in the downloaded folder, or `--observations` | Only after a yes, or with `--yes`. Appended to, one line per paste; a later paste does not replace an earlier one |
| Hand-taken copies of the desktop file | `ledger/plan-usage/`, if you make one | Read, not written |

The last two are listed in `.gitignore`.
