#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Classification: what a record says about itself, and to whom it applies.

This is the cleaned copy that ships with the package. The register's own
`store/governance.py` carries a second half, presentation mode, which redacts
identifying values out of an export. **That half is deliberately not shipped.**

Redaction here is two halves: redact by named field, then check the result
against a private list of client and company names. The second half cannot run
for anyone but its author -- it refuses unless it finds that list at a fixed
path outside the repository, and it refuses by design, because a check with
nothing to look for finds nothing and "found nothing" reads exactly like a pass.
Shipping the redactor without the check would offer a clean-looking export with
nothing standing behind it, from a snapshot that says on its own front page it
may never be updated. A redactor that misses something is worse than no
redactor, because it was trusted.

So this package does not redact, and `store.py --export` says plainly when an
export carries values that could identify a person or a project.

## Classification

The governance block is the set of fields a client asks to see: which tier the
work sits in, whether it is an AI system, what role you hold, and whether its
output reaches a third party. This makes those fields queryable -- which
projects are classified, which are not, and which are missing a field the stage
they have reached already owes.

The vocabularies live in `store.CLASSIFICATION_VOCABULARY` and which stage owes
which field is read out of `store.STAGE_REQUIREMENTS`. Nothing is restated here:
a second list of the four fields is a second place to be wrong.

**`is_ai_system` is three-valued -- yes | no | contested -- and never a bool.**
`store._coerce` already refuses the collapse. "contested" is the honest answer
for a system whose classification is argued about, which is most of the
interesting ones, and a boolean has nowhere to put it. There is a test.

**Refs carry no meaning, by design.** `P-0007` says nothing about the project it
names, so a ref is the way to talk about a record in front of someone who may
not see its name.

    python3 store/governance.py                 # what the register knows about classification
    python3 store/governance.py --queries       # the classification queries
    python3 store/governance.py --show P-0001
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import store  # noqa: E402


# --------------------------------------------------------------------------
# Classification queries
# --------------------------------------------------------------------------

def classify_store(loaded):
    """Every project's governance block, in ref order."""
    return {ref: store.classify(project["fields"])
            for ref, project in sorted(loaded["projects"].items())}


def classification_queries(loaded):
    """The questions the governance block exists to answer.

    Each returns refs, never records: a query result that carries names is a
    query result that cannot be shown in front of anyone.
    """
    classified = classify_store(loaded)
    by_tier = {}
    for ref, result in classified.items():
        tier = result["fields"]["act_tier"]["value"] or "unclassified"
        by_tier.setdefault(str(tier), []).append(ref)
    return {
        # Missing a classification a stage already owes. A subset of stage debt
        # rather than a new opinion about what is owed.
        "missing_at_a_stage_that_owes_it": {
            ref: result["missing_and_owed"]
            for ref, result in classified.items() if result["missing_and_owed"]},
        # Never classified at all. Different from the above and reported
        # differently: a captured shower thought owes nothing yet, and saying
        # "missing" about it would be a thirty-field form again.
        "never_classified": [ref for ref, result in classified.items()
                             if result["unclassified"]],
        # A value outside the vocabulary. store.check() calls this a problem;
        # here it is a list.
        "invalid_values": {ref: result["invalid"]
                           for ref, result in classified.items() if result["invalid"]},
        "by_act_tier": {tier: sorted(refs) for tier, refs in sorted(by_tier.items())},
        # The three-valued field, kept three-valued. "contested" is a real
        # answer and it is the one worth a list of its own.
        "contested": [ref for ref, result in classified.items()
                      if result["fields"]["is_ai_system"]["value"] == "contested"],
        "ai_systems": [ref for ref, result in classified.items()
                       if result["fields"]["is_ai_system"]["value"] == "yes"],
        # `both` is listed apart from `provider` deliberately: it IS provider for
        # the purpose of the question, and collapsing the two would throw away a
        # distinction the vocabulary makes on purpose. A project that has never
        # been classified is listed rather than assumed to be a deployer.
        "provider_not_deployer": _by_role(classified),
        # third_party_output is the field that decides whether anything leaves
        # the building. Worth asking on its own.
        "output_reaches_a_third_party": [
            ref for ref, result in classified.items()
            if result["fields"]["third_party_output"]["value"] in ("client", "published")],
        "complete": [ref for ref, result in classified.items() if result["complete"]],
    }


def _by_role(classified):
    """my_role, split into its own vocabulary and nothing else."""
    buckets = {"provider": [], "both": [], "deployer": [],
               "not_applicable": [], "unclassified": []}
    for ref, result in classified.items():
        value = result["fields"]["my_role"]["value"]
        if value == "provider":
            buckets["provider"].append(ref)
        elif value == "both":
            buckets["both"].append(ref)
        elif value == "deployer":
            buckets["deployer"].append(ref)
        elif value == "n/a":
            buckets["not_applicable"].append(ref)
        else:
            buckets["unclassified"].append(ref)
    return {name: sorted(refs) for name, refs in buckets.items()}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Classification.")
    parser.add_argument("--root", default=str(store.ROOT))
    parser.add_argument("--queries", action="store_true")
    parser.add_argument("--show", metavar="REF")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv=None, out=None):
    args = parse_args(argv)
    out = out or sys.stdout
    root = Path(args.root)
    register = store.RefRegister.load(root / "store" / "refs.json")
    loaded = store.load_store(root)

    def say(line=""):
        print(line, file=out)

    if args.show:
        ref = register.resolve(args.show)
        if ref not in loaded["projects"]:
            say(f"{args.show}: not a project in the store.")
            return 1
        result = store.classify(loaded["projects"][ref]["fields"])
        if args.json:
            say(json.dumps(result, indent=2, sort_keys=True))
            return 0
        say(f"{ref}  stage {result['stage']}")
        for field, detail in result["fields"].items():
            mark = {"set": " ", "missing": "?", "invalid": "!"}[detail["state"]]
            owed = (f"owed from {detail['owed_from']}"
                    if detail["owed_now"] else f"not owed until {detail['owed_from']}"
                    if detail["owed_from"] else "no stage owes it")
            say(f" {mark} {field:<20} {str(detail['value']):<14} {owed}")
        say("complete." if result["complete"] else
            f"missing and owed: {', '.join(result['missing_and_owed']) or 'none'}")
        return 0

    queries = classification_queries(loaded)
    if args.json or args.queries and args.json:
        say(json.dumps(queries, indent=2, sort_keys=True))
        return 0
    if args.queries:
        for name, result in queries.items():
            say(f"{name}")
            if isinstance(result, dict):
                for key, value in result.items():
                    say(f"  {key}: {', '.join(value) if isinstance(value, list) else value}")
            else:
                say(f"  {', '.join(result) or '-'}")
            say()
        return 0

    classified = classify_store(loaded)
    say(f"classification  {len(classified)} project(s), "
        f"{len(queries['complete'])} complete, "
        f"{len(queries['never_classified'])} never classified")
    for ref, result in classified.items():
        block = "  ".join(
            f"{field}={result['fields'][field]['value']}"
            for field in store.CLASSIFICATION_FIELDS)
        say(f"{ref}  {result['stage']:<12} {block}")
    for ref, missing in queries["missing_at_a_stage_that_owes_it"].items():
        say(f"owed     {ref}: {', '.join(missing)} -- the stage already owes these")
    for ref, invalid in queries["invalid_values"].items():
        say(f"PROBLEM  {ref}: {', '.join(invalid)} outside the vocabulary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
