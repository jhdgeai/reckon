# Clean-machine test run

Run on 27 September 2026 against commit `7d1c9f9` (Reckon v1.2.1, the head of `main`). No file in the
repository was changed; each run used a fresh `git clone` of that commit.

## How the tests are meant to be run

The README ("Tests"), `docs/SETTINGS.md` ("Running the tests") and `.github/workflows/tests.yml` agree:
five separate `unittest` discoveries from the top of the repository, inside the virtual environment
the Quickstart builds (`python3 -m venv .venv`, upgrade pip, `pip install -e .`).

```sh
python -m unittest discover -s store/tests
python -m unittest discover -s wrapper/tests
python -m unittest discover -s estimator/tests
python -m unittest discover -s ledger/tests
python -m unittest discover -s reckon/tests
```

There is no pytest configuration and no test runner beyond this. CI runs the same five commands on
Python 3.9 on `ubuntu-latest`.

## The machine

A Linux container (kernel 6.18, x86_64), user `root`, `HOME=/root`, time zone UTC, no `LANG` set, no
Claude Code transcripts in `~/.claude`, no network needed. The default `python3` is 3.11.15. For the
second run I installed CPython 3.10.18 with `uv python install 3.10` and built a new venv from it.

## Counts

| Python | Passed | Failed | Errored | Skipped |
|---|---|---|---|---|
| 3.11.15 | 757 | 0 | 0 | 1 |
| 3.10.18 | 757 | 0 | 0 | 1 |

Both runs executed 758 tests, and every suite exited 0.

| Suite | Tests | Result (both versions) |
|---|---|---|
| store | 307 | OK |
| wrapper | 97 | OK |
| estimator | 26 | OK, 1 skipped |
| ledger | 288 | OK |
| reckon | 40 | OK |

I also ran all five suites on 3.11 with `TZ` set to Europe/London, America/Los_Angeles,
Pacific/Kiritimati (UTC+14) and Pacific/Pago_Pago (UTC-11), and once from a fresh clone with the
system Python and no venv or `pip install -e .` at all. Every one of those runs gave the same
result: all pass, one skip. The tests that touch time build their own fixed UTC clock (for example
`NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)` in `ledger/tests/test_statusline.py`), which
is why the time zone makes no difference. After each run `git status` showed nothing but ignored
files (`.venv/`, `__pycache__/`, `reckon.egg-info/`), so the tests do not write into the checkout.

## Findings, worst first

There are no failures and no errors on either Python version, so there is nothing to classify as a
real bug, a Mac-only assumption or a flaky test in the sense the brief asked for. What follows are
the places where a green run on a clean machine tests less than it appears to.

### 1. One test is skipped because it needs a file from the author's own folder

`estimator/tests/test_estimate.py`,
`TestRenderedWording.test_rendered_output_carries_no_tell_tale_word`, skipped on both versions.

The reason printed is: "needs the register's own build-time word list, which a package built from it
does not carry". The path it looks for is outside the repository:

```python
TELL_TALE_PATH = Path(__file__).resolve().parents[2] / "package" / "tell-tale-words.json"
```

`parents[2]` of `estimator/tests/test_estimate.py` is the folder that contains the `reckon` checkout,
so the test only runs where a sibling folder called `package/` holds that JSON file. No file named
`tell-tale-words.json` exists anywhere in the repository's history. My judgement: a test that assumes
the author's own local folder. It does not fail, it skips, and the only sign is `OK (skipped=1)` in
the estimator suite's last line. Nobody outside the author's machine, CI included, runs this check.

### 2. One test passes on a clean checkout without checking anything

`store/tests/test_decision_owed.py`,
`OnePropositionNotAChoice.test_every_open_question_in_the_real_store_is_a_proposition`.

Its docstring says "The audit, against the records on disk rather than a fixture":

```python
for item in S.decisions_owed(S.load_store(ROOT)):
    padded = f" {item['decision_owed'].lower()} "
    for word in (" or ", " whether "):
        self.assertNotIn(word, padded, item["ref"])
```

On a fresh clone `S.decisions_owed(S.load_store(ROOT))` returns an empty list (I called it directly:
`decisions_owed: 0`), because the `projects/`, `tasks/` and `decisions/` records it audits are the
author's own and `.gitignore` excludes `decisions/`. The loop body never runs and the test reports
`ok` with no assertion made. My judgement: a test that assumes the author's own data; a silent pass
rather than a skip, so it is less visible than finding 1.

### 3. The store suite leaves 43 temporary folders behind on every run

Counting `/tmp/tmp*` before and after each file:

| File | Folders left |
|---|---|
| test_integrity.py | 35 |
| test_outcome.py | 5 |
| test_decision_owed.py | 3 |

The cause is `tempfile.mkdtemp()` with no matching cleanup: `Tree.__init__` at
`store/tests/test_integrity.py:42` and line 415, `store/tests/test_outcome.py:243` and
`store/tests/test_decision_owed.py:143`. The other four suites leave nothing. My judgement: a minor
real defect in the tests. It does not affect results, but the folders accumulate on a developer's
machine with every run.

### 4. Three ResourceWarnings in the store suite

Running the store suite prints, three times:

```
/usr/lib/python3.11/tempfile.py:1073: ResourceWarning: Implicitly cleaning up <TemporaryDirectory '/tmp/...'>
```

They come from `store/tests/test_store.py:1122`, in `PreferencesCarriedIntoARun._sources`, which
creates a `tempfile.TemporaryDirectory()` and never calls `cleanup()`; Python tidies it up at garbage
collection and warns. The same three warnings appear on 3.10. Harmless to the result, but it is noise
in an otherwise silent run. Same judgement as finding 3.

### 5. Coverage of the documented minimum was not exercised here

`pyproject.toml` says `requires-python = ">=3.9"`, the Quickstart says the author tested on the
Command Line Tools' Python 3.9.6, and CI pins 3.9. This review ran 3.11 and 3.10 as briefed, so 3.9
is covered only by CI. Nothing in either run suggested a version-specific problem: the counts and
results were identical on both.

## Nothing found in these areas

I searched every test file for macOS paths and tools (`/Users/`, `Library`, `Application Support`,
`sw_vers`, `osascript`, `pbpaste`, `darwin`, `sys.platform`, `/opt/homebrew`). The `/Users/x/...`
strings that appear are fixture data written into temporary files, and the `~/.claude` references
are assertions about configuration text or `expanduser()` on a path that is never read. None of them
depends on the machine being a Mac, which the Linux pass confirms.
