# Changelog

## 1.2.1

The rest of 1.2.0.

- **`reckon status`: where both limits stand now**, from every source that has a reading, each
  with its source, its age and its reset time where the source has one. A reading older than its
  own window is named and not shown. See [the usage meter](docs/USAGE.md).
- **A warning at 80 per cent** of either limit, in words, with when the readings project it to
  reach 100. No weekly projection from readings either side of 13 September 2026.
- **A status line** (`ledger/statusline.py`) that shows both percentages in Claude Code and keeps
  each reading with its reset time, for Claude Code in a terminal. It is off until you add it to
  your Claude Code settings, and it has not yet been seen running live. The Claude desktop app does
  not run status lines; there, paste the usage page with `reckon usage --paste`.
- **`reckon report` ends with the last seven days**: Claude Code's measured cost beside the account
  meter for the same days, with the sentence that the measured cost is a floor.
- The repository moved to github.com/jhdgeai/reckon when its owner's account was renamed.
  GitHub redirects the old address.

## 1.2.0

- **`reckon usage`: the account's own usage meter.** It reads the five-hour and weekly percentages
  from the file the Claude desktop app keeps on a Mac, one block per account, with the gaps where
  the app was closed and how much of its span the file covers. `--paste` reads a pasted copy of
  the usage page in Claude's settings, for the reset times and the split by product, and saves it
  only after a yes. `--archive` keeps the samples after the app drops them. See
  [the usage meter](docs/USAGE.md).
- It turns no percentage into money, writes no account identifier down, and does not join weekly
  percentages across 13 September 2026, when the weekly limit changed.
- The rest of 1.2.0 (a status line, a `reckon status` command, a warning at 80 per cent, and the
  report joining the meter to recorded cost) is not in this release.

## 1.1.1

What a newcomer tripped over, following the 1.1.0 pages on a Mac's own Python 3.9 and its pip:

- **The install works with the Python that comes with macOS.** The Quickstart now gives the whole
  path: the clone command, `cd reckon`, a Python environment in the folder, a pip upgrade, then
  `pip install -e .`. The pip that comes with Apple's Command Line Tools could not install this
  folder, and macOS has no `pip` or `python` command until an environment is active. It also says
  where `python3` and `git` come from on macOS, how to check the Python version, and what the
  install was tested on.
- **Which sessions `reckon record` can see:** every Claude Code session still on the computer,
  including earlier ones, and none that Claude Code has already deleted; and that recording is not
  automatic.
- **Your own work.** `docs/QUICKSTART.md` shows how to record your own sessions, what `reckon report`
  then says, and how to copy a sample task, change its fields and gate it.
- **`reckon report` on a store with no tasks says so,** with the number of runs recorded and their
  total at list rates, instead of reading the same as a store where nothing ran over.
- **The captured output matches what a newcomer sees.** The gate's form without Claude Code is shown
  beside the form with it, the exit codes for allow, ask and block are stated, and parts that differ
  per computer are marked. `reckon record --help` names `~/.claude/projects` as its default.
- **A clean folder.** A `.gitignore` covers the environment, the install's own files and what
  `reckon record` writes, and the Quickstart says that `record` writes into the downloaded folder.
- The reckon tests no longer print an error message and a help screen while passing.
- The documents give plain reasons in place of references to an unpublished spec.

## 1.1.0

- **One command, `reckon`,** over `estimate`, `gate`, `record` and `report` -- each subcommand
  a thin wrapper over the module that already did the work; no calculation was copied.
- **The only supported install is `pip install -e .`** from a downloaded copy; run any other way,
  `reckon` refuses and names the line to use.
- **`docs/QUICKSTART.md`** -- install, then every command, with its own captured output.
- **`reckon report`** lists any task whose recorded cost is more than 10% over its estimate, on the
  face saying these are list-price estimates and a floor, not a bill.
- **The sample's gate table is the real gate's own answer,** run on copies of three sample tasks
  with their state changed to `approved` -- the tasks themselves are shipped, and the same gate
  blocks a shipped task on sight. `sample/tasks/` and `sample/session/` ship those copies and one
  invented Claude Code session, each marked as such in its first line.
- Wording fixes so the estimator's and the walkthrough's own text pass this package's language
  check.

## 1.0.0

- First published snapshot: the data model, the cost gate, the estimator, and the ledger reader,
  with a redacted sample and the getting-started, data-model and method documents.
