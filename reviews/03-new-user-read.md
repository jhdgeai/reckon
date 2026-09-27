# Reckon 1.2.1: a new user's read of the documentation

Reviewed on 27 September 2026, against `main` at commit `7d1c9f9`. I read README.md, every file in
`docs/`, CHANGELOG.md, `sample/SAMPLE.md` and `writing/what-the-register-measured.md`, ran
`reckon --help` and `--help` on all six subcommands, and ran every command in the Quickstart on a
scratch clone (Linux, Python 3.11, Claude Code installed). This judges the documentation only. Where
I looked at code, it was to check whether a document is true.

## Verdict

Reckon is worth trying for a Mac user who runs Claude Code and wants to know what their sessions
cost at list prices, and its documents are unusually candid about their own limits, but they are
written from inside the author's setup: a newcomer meets undefined terms in the first screen, captured
output that no longer matches the program, and settings instructions that only work on the author's
machine.

## The five changes that would help a new user most

1. Rewrite the first screen to say what Reckon is, who it is for and what it needs. Today the
   opening sentence promises "a log of all the work you do in Claude Code", which the Quickstart
   contradicts (recording is manual, sessions older than 30 days are gone, the desktop app and web
   are not seen). It does not say Reckon is a command-line tool, that it prices in US dollars, that
   the install is written for macOS only, or that `reckon usage` reads a Mac-only file. A short
   "You need" table (macOS, Python 3.9+, git, Claude Code, optionally the Claude desktop app) would
   answer most of question two in section A below.
2. Say plainly, near the top, that every estimate and every gate decision comes from the author's
   history, not yours. `estimator/model.json` is fitted to 27 of the author's tasks and the gate's
   `priors` are the author's session costs. SETTINGS.md tells you to re-derive both, but
   `python estimator/estimate.py --fit` crashes on a fresh copy (it needs
   `ledger/preflight-ledger.md`, which is not shipped) and `--priors --write-priors` derives nothing
   without `ledger/run-tasks.json`, which no document explains. A new user cannot yet make the
   estimator theirs, and should be told so.
3. Make the documents agree with the program and with each other in one pass: regenerate the
   `reckon estimate` capture in QUICKSTART.md, fix the "from 1.2.0" claims for `reckon status`,
   settle "six times" against "ten times", correct the split rule in METHOD.md §5, and add the
   missing `reckon usage`, `reckon status` and block captures. Section D lists each one.
4. Add a short glossary and link it from the README. Turns, p50, p95, list rates, rail, brief,
   floor, register, held, leave-one-out, front matter and priors all appear in the README or the
   first command's output before any document defines them.
5. Say what `reckon gate --execute` does to your computer, and what path exists from the sample to
   your own records. It starts Claude Code unattended with `Bash`, `Edit` and `Write` allowed and
   `--permission-mode acceptEdits`, in whatever folder you run it from; no document says so. And
   the compliance record-keeping the README advertises (projects, approvals, exports with consent)
   is only reachable through `store/store.py`, whose command line no document mentions.

## The full list

### A. The questions a newcomer asks

**What does it do, in one sentence?** Reckon is a Python command-line tool that prices a Claude Code
task in US dollars before it runs, can hold a scripted task for a person's approval, and afterwards
reads Claude Code's local transcripts to record each session's cost at list prices, so that
estimates can be checked against actuals.

**Does the README say that in its first screen?** Partly. Line 5 reads "Reckon creates a log of all
the work you do in Claude Code (the AI coding assistant) and estimates its token cost before it
starts." That covers recording and estimating. It leaves out the gate, which is the thing that acts,
and it overstates in two places: the log is not of "all the work" (QUICKSTART.md lines 234 to 238:
nothing is recorded automatically, deleted and non-Claude Code sessions are not seen), and the
estimate is in dollars and turns, not tokens. The first screen does not say it is a command-line
tool. The "Why" section at line 37, one scroll down, is the clearer description.

**Who is it for?** No document says. The evidence points two ways. The Quickstart, the usage meter
and the tested setup (QUICKSTART.md line 10, macOS 26.4) point to an individual on a Mac with a Claude
subscription. README line 50 addresses "Organisations deploying AI tools" that "need to capture their
AI use cases", but no document shows an organisation how to capture a project, record an approval or
write an export. README line 8 calls it a snapshot "for others to review and try out", which is the
most honest statement of audience and is easy to miss.

**What does it need?**

| Need | Stated? | Where |
|---|---|---|
| macOS | Implied | README line 14 |
| Linux, Windows | Not stated | CI runs Ubuntu |
| Python 3.9+ | Yes | README line 14 |
| git | Yes | QUICKSTART line 5 |
| Claude Code | Partly | README line 135 |
| Desktop app | For `usage` | USAGE line 14 |
| Subscription | Implied | USAGE line 120 |
| Any account | Reckon: none | README line 72 |

On Linux every command in the Quickstart worked for me except `reckon usage` and `reckon status`,
which found no source because they look under `~/Library/Application Support`. The documents neither
promise nor rule out Linux or Windows.

Folders it reads and writes are spread across four documents. Collected: it reads
`~/.claude/projects` (transcripts), `~/.claude/CLAUDE.md` (fingerprint only) and
`~/Library/Application Support/Claude/plan-usage-history.json`; it writes `ledger/runs.json`,
`runs/`, `store/refs.json` and `decisions/` inside the downloaded folder (QUICKSTART.md line 152),
`~/Library/Application Support/claude-ledger/plan-usage/` with `--archive` (USAGE.md line 171), and
you add a line to `~/.claude/settings.json` for the status line (USAGE.md line 129). The fact that
data lives inside the code folder, so deleting or re-cloning the folder deletes your records, is
stated as a reason for the install method (QUICKSTART.md line 34) but never as a warning.

**What will it not do?** This is the documentation's strongest part. README lines 54 to 85 list
ten things it is not, including not a bill, not maintained, no redaction, no tamper-proofing, the
gate not covering conversations, and the program being offline while the way you drive it is not.
USAGE.md lines 154 to 165 do the same for the meter. Gaps: nothing says what happens to a session on a
model missing from `ledger/prices.json` (it was last checked on 4 September 2026 and has no
`claude-opus-5-5` entry), and nothing says `--execute` runs an unattended agent with shell access.

**Are the figures explained, including that they are estimates and not bills?** Yes, repeatedly and
well: README line 46 and 58, every command's own output ("client-side estimate, not a bill"), METHOD.md
§4 and the report's standing paragraph. The weaker points: "a floor on what the account loses" in the
`reckon estimate` output is odd wording for "at least this much"; "Not sterling" is printed while the
session ceiling in `wrapper/gate.json` is in pounds; the README never says the range is meant to hold
the real figure 80% of the time (that is only in METHOD.md §6); and nothing near the estimate says it
is the author's history speaking.

### B. Terms used before they are explained

In reading order. "Never" means no shipped document defines it.

1. "token cost" (README line 6). Tokens are not explained; the figures are dollars.
2. "redacted core" (README line 9). Redacted from what is not said until line 96.
3. "gate" (README line 44). Explained at line 93.
4. "The Recorder" (README line 45), capitalised as a component. Never named again in the README.
5. "list rates" / "list prices" (README line 46). Never defined; SETTINGS.md line 32 implies
   published per-million-token prices.
6. "scripted tasks" (README line 64). Means a task file sent through `claude -p`; first shown in
   QUICKSTART.md line 90.
7. "headroom" and "the points where requests were refused" (README line 68). Never.
8. "usage meter" (README line 69). Explained in USAGE.md line 6.
9. "baseline", "re-take the baseline" (README line 80). Never.
10. "version history" and "forbidden by rule" (README line 81). Which rule is never said.
11. "tier", "AI system", "what role you hold", "third party" (README line 92). No framework is named
    and none of the four is defined anywhere.
12. "Projects, Tasks, Runs and Decisions" (README line 92). Defined in DATA-MODEL.md.
13. "brief" and "kind of task" (README line 93). "Class" is used for the same idea in METHOD.md
    line 19. Never defined; the classes (`code-task`, `investigation`, `html-artifact`) appear only
    in `wrapper/gate.json`.
14. "five-hour and weekly limits" (README line 95). Explained in USAGE.md.
15. "turns" (README line 108, first output). METHOD.md line 10 equates it with assistant messages;
    the README never does.
16. "p50", "low", "high" (README lines 112 to 114). Never.
17. "hit rate", "leave-one-out" (README lines 116 and 117). Described, not named, in METHOD.md §6.
18. "a floor on what the account loses", "Not sterling" (README line 119).
19. "p95", "est_p95_usd", "front matter" (README line 126). "95th percentile" appears in
    DATA-MODEL.md line 21; "front matter" is never explained.
20. "rail", "subscription" (README line 129). "Billing rail" in DATA-MODEL.md line 24 and
    `ledger/rails.json`; never defined in words.
21. `--allowedTools`, `--permission-mode acceptEdits` (README line 130). Never; `reckon gate --help`
    gives no help text for them or for `--scheduled` and `--gate-config`.
22. "register" (`reckon --help`: "the register's own estimator"; report output: "This register sees
    Claude Code only"). Never; the documents say "store".
23. "held", "fingerprint", "task ref", "default rail", "outputs" (`reckon record` output).
    QUICKSTART.md lines 181 to 192 explain three of these; "task ref" and "outputs" are not.
24. Two run identifiers, `R-10203040` and `R-0001`, in the same `reckon record` output. The
    difference is never explained.
25. "priors", "realisation factor", "ridge regression" (METHOD.md §5, SETTINGS.md line 27).
26. "stage", "stage gates", "stage transitions" (DATA-MODEL.md lines 10 and 41). The stages are
    never listed; only `prototype` is given as an example.
27. "export", "manifest", "consent" (README line 84, DATA-MODEL.md line 46). No document says how to
    make an export.
28. "purge", "candidate", "held" in a second sense, "risk" (SETTINGS.md lines 34 to 37). Purge is
    never described as a feature, and `risk/` is never mentioned elsewhere.
29. "Cross-check ... observed seven-day ceiling, from 7 refusal(s)" (USAGE.md line 94). Partly
    explained at line 102; how to produce one is not.
30. "Cowork" (USAGE.md line 72). Never.

### C. Instructions that only work on the author's machine

1. SETTINGS.md line 38: "run `python estimator/estimate.py --fit`". On a fresh copy it stops with
   `FileNotFoundError: ... ledger/preflight-ledger.md`. That file is not shipped.
2. SETTINGS.md line 27: "run `python ledger/recorder.py --priors --write-priors`". On a fresh copy
   it prints `{}` and rewrites the shipped priors' `source` labels to `hand-carried`, because it
   needs `ledger/run-tasks.json`, which is not shipped and not documented. Its `--source` default is
   "the archive", the author's transcript archive.
3. `store/purge.json` `candidate_roots.transcripts` is
   `~/Library/Application Support/claude-ledger/archive`, the author's archive. SETTINGS.md line 37
   calls it "A transcript archive folder" without saying nothing ships to create or fill it.
4. `reckon record --help` names `ledger/archive-config.json` as an alternative default. No document
   mentions that file.
5. `reckon record` output tells you to "add the link in ledger/run-tasks.json". No document says
   what that file looks like.
6. `reckon status` output says "ledger/limits.py writes one" for the cross-check. No document says
   how to run it or what it reads.
7. METHOD.md §1, "the session states its estimate out loud", and §3, the session ceiling as "a rule
   a session follows" (SETTINGS.md line 40). Nothing shipped makes a session do either; on the
   author's machine this presumably comes from their own Claude Code instructions.
8. README line 81, "rewriting that is forbidden by rule": the author's rule, not one Reckon ships.
9. USAGE.md line 14 onwards: the meter file and archive paths exist only on a Mac with the Claude
   desktop app. On Linux both are reported absent.
10. The estimator and gate figures shown throughout (`model.json`, `gate.json` priors) are fitted
    to the author's history, and items 1 and 2 mean a new user cannot refit them.
11. References to the author's unpublished spec survive: `store/purge.json` ("spec-v0.2.md §8.5"),
    `sample/tasks/P-0001-T09.md` ("§5.3"), `python store/store.py --help` ("spec §8.3"), and
    `ledger/prices.json` cites "TASK-001-ledger.md price table" as its source.
12. `wrapper/gate.json` and `store/purge.json` give "See docs/METHOD.md." as the basis for the $10
    threshold, the $5 cap, three samples and 90 days. METHOD.md gives no basis for any of them, so
    the basis sits with the author.

### D. Broken or dead links

Every relative link in README.md, CHANGELOG.md and `docs/` resolves to a file that exists. The
repository address answered from this environment; the Actions page and badge returned 403 through
this session's network proxy, so I could not confirm them. Dead ends that are not links:

1. QUICKSTART.md line 37 says the install refusal is covered in "[SETTINGS](SETTINGS.md)".
   SETTINGS.md says nothing about it.
2. The twelve "See docs/METHOD.md." basis fields (nine in `wrapper/gate.json`, three in
   `store/purge.json`), as in C12.
3. CHANGELOG.md line 23 says GitHub redirects "the old address" without naming it.

### E. Places where two documents disagree

1. The `reckon estimate` capture. README lines 108 to 114 show pieces at $8.26 and $2.75 and a range
   of $3.37 to $35.03, which is what the program printed for me. QUICKSTART.md lines 53 to 59, which
   README line 34 calls "actual captured output", show $8.14 and $8.14 and a range of $4.89 to
   $52.45.
2. When `reckon status` arrived. README lines 68 to 69 and line 91 say "from 1.2.0". CHANGELOG.md
   line 36 says it "is not in this release" (1.2.0) and lists it under 1.2.1; USAGE.md line 83 says
   "New in 1.2.1".
3. The width of the estimator's range. README line 66: "about ten times the bottom", as does the
   writing sample (line 68, "in money"). METHOD.md line 80: "about six times its bottom". Neither
   says whether it means turns or dollars.
4. Output's share of cost. METHOD.md line 11: "about a seventh" (about 14%). The writing sample,
   line 20: 17%, which is about a sixth.
5. The split rule. METHOD.md line 51 says the estimator splits on "a comma followed by 'and'". The
   README's own example, "Add a --json flag to an existing CLI subcommand, with a test.", splits at
   ", with", so the documented rule is not the one the program uses.
6. What the Quickstart contains. README line 34 promises "every command's actual captured output".
   QUICKSTART.md's `reckon usage` section (line 222) shows the command with no output, and
   `reckon status` has no section at all.
7. The gate answers shown. README line 137 says QUICKSTART.md captures "the other two `reckon gate`
   answers". QUICKSTART.md shows ask, allow and ask again; block, and its exit code 3, never appear.
8. How much is logged. README line 5, "a log of all the work you do in Claude Code", against
   QUICKSTART.md lines 234 to 238 and README line 59.
9. Currency. `reckon estimate` prints "Not sterling" and the gate threshold is $10; the session
   ceiling in METHOD.md line 35 and SETTINGS.md line 29 is £10. No document explains the mix.
10. How to measure sessions. SETTINGS.md line 15 names `ledger/aggregate.py` and
    `ledger/recorder.py`; QUICKSTART.md uses `reckon record`. SETTINGS.md step 4 predates the
    single command and was not updated.
11. Unpublished-spec references. CHANGELOG.md line 62 (1.1.1) says the documents "give plain reasons
    in place of references to an unpublished spec"; the files in C11 still carry them.
12. Creating your own records. QUICKSTART.md line 264 says this version "does not create" task
    records for you, and README line 92 says the store "requires a recorded consent before an export
    is written". `store/store.py` has `--capture`, `--capture-task`, `--transition` and `--export`,
    so the capability exists and the documents both deny and advertise it without showing it.
13. The gate's handling of shipped tasks. QUICKSTART.md line 72 says "the tasks themselves
    shipped", which reads as "shipped with the package"; SAMPLE.md line 26 makes clear it means the
    state `shipped`. The Quickstart wording is ambiguous where SAMPLE.md is not.
