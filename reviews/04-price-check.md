# Price check: Reckon against Anthropic's published API prices

Checked on 27 September 2026 against `main` at commit `7d1c9f9` (Reckon v1.2.1).

## Verdict

Every per-token rate the repository holds matches Anthropic's published list price today, but the table has no row for Claude Opus 5.5 (`claude-opus-5-5`), so every session on that model is costed at $0.00.

## Sources

| Page | URL | Read (UTC) |
| --- | --- | --- |
| Docs pricing | https://platform.claude.com/docs/en/about-claude/pricing (and its `.md` form) | 27 Sep 2026, 09:10 |
| Pricing page | https://www.anthropic.com/pricing, which redirects to https://claude.com/pricing | 27 Sep 2026, 09:10 |
| Model IDs | https://platform.claude.com/docs/en/about-claude/models/overview | 27 Sep 2026, 09:10 |
| Deprecations | https://platform.claude.com/docs/en/about-claude/model-deprecations | 27 Sep 2026, 09:10 |

The docs pricing page is the fuller of the two: it lists 18 models with all five rates. The claude.com pricing page lists 12 of them (no Mythos, no retired models) with input, output, 5-minute cache write and cache read, and every figure it shows agrees with the docs page.

## Where prices are held

There is one price table, `ledger/prices.json`, in US dollars per million tokens. `ledger/aggregate.py` loads it (`PRICES_PATH`, line 26) and it is the only source of per-token rates for `aggregate.py`, `recorder.py` and `limits.py`. `docs/SETTINGS.md` line 32 describes it but holds no figures.

Other dollar figures exist, but none is a per-token price. `estimator/model.json` holds a fitted cost curve (`a_per_message`, `b_per_message_squared_over_100`) derived from past Run records, `estimator/estimate.py` line 494 adds a measured $1.20 per session restart, and `wrapper/gate.json` holds thresholds and past-run samples in dollars. All of them inherit whatever the price table produced, so a gap in the table flows into them, but none can be checked against a list price.

The table holds no long-context rate for any model, and no fast-mode, batch or data-residency rate.

| Model (prices.json line) | Input / output | 5m / 1h write | Cache read |
| --- | --- | --- | --- |
| claude-fable-5-1 (8) | 10 / 50 | 12.50 / 20 | 0.25 |
| claude-mythos-5-1 (15) | 10 / 50 | 12.50 / 20 | 0.25 |
| claude-fable-5 (22) | 10 / 50 | 12.50 / 20 | 1.00 |
| claude-mythos-5 (29) | 10 / 50 | 12.50 / 20 | 1.00 |
| claude-opus-5 (36) | 5 / 25 | 6.25 / 10 | 0.50 |
| claude-opus-4-8 (43) | 5 / 25 | 6.25 / 10 | 0.50 |
| claude-opus-4-7 (50) | 5 / 25 | 6.25 / 10 | 0.50 |
| claude-opus-4-6 (57) | 5 / 25 | 6.25 / 10 | 0.50 |
| claude-opus-4-5 (64) | 5 / 25 | 6.25 / 10 | 0.50 |
| claude-sonnet-5 (71) | 2 / 10 | 2.50 / 4 | 0.20 |
| claude-sonnet-4-6 (78) | 3 / 15 | 3.75 / 6 | 0.30 |
| claude-sonnet-4-5 (85) | 3 / 15 | 3.75 / 6 | 0.30 |
| claude-haiku-4-5 (92) | 1 / 5 | 1.25 / 2 | 0.10 |
| claude-opus-4-1 (99) | 15 / 75 | 18.75 / 30 | 1.50 |
| claude-opus-4 (106) | 15 / 75 | 18.75 / 30 | 1.50 |
| claude-sonnet-4 (113) | 3 / 15 | 3.75 / 6 | 0.30 |
| claude-3-7-sonnet (120) | 3 / 15 | 3.75 / 6 | 0.30 |
| claude-3-5-sonnet (127) | 3 / 15 | 3.75 / 6 | 0.30 |
| claude-3-5-haiku (134) | 0.80 / 4 | 1 / 1.60 | 0.08 |
| claude-3-opus (141) | 15 / 75 | 18.75 / 30 | 1.50 |
| claude-3-haiku (148) | 0.25 / 1.25 | 0.30 / 0.50 | 0.03 |

The table also lists `<synthetic>` under `ignored_models` (line 157), which Claude Code writes for messages with no model call.

## Mismatches

I compared the 17 models that appear on both the repo table and the docs page, five rates each, by script as well as by eye. All 85 figures agree. The mismatches are a missing model, four models no longer published, and one stale sentence.

| Model and location | Rate | Repo | Published |
| --- | --- | --- | --- |
| claude-opus-5-5, prices.json: no row | Input | none | $4 |
| claude-opus-5-5, prices.json: no row | Output | none | $20 |
| claude-opus-5-5, prices.json: no row | 5m write | none | $5 |
| claude-opus-5-5, prices.json: no row | 1h write | none | $8 |
| claude-opus-5-5, prices.json: no row | Cache read | none | $0.20 |
| All models, prices.json line 6 | Cache-read note | 0.1x except Fable 5.1 and Mythos 5.1 | Also 0.05x on Opus 5.5 |

Anthropic publishes one model the repo cannot price: Claude Opus 5.5, API ID `claude-opus-5-5`. The docs page lists it in the model pricing table, claude.com lists it second, and the models overview names it as the recommended starting model. Its cache read is 0.05x input, a third exception to the 0.1x rule that the note at `prices.json` line 6 does not mention.

Claude Mythos Preview (`claude-mythos-preview`, marked deprecated on the deprecations page) also has no row, but Anthropic publishes no per-token price for it either, so there is nothing to compare.

The repo prices four models Anthropic no longer lists on either pricing page: `claude-3-7-sonnet` (line 120), `claude-3-5-sonnet` (line 127), `claude-3-opus` (line 141) and `claude-3-haiku` (line 148). The deprecations page shows all four retired (3.5 Sonnet on 28 October 2025, 3 Opus on 5 January 2026, 3.7 Sonnet on 19 February 2026, 3 Haiku on 20 April 2026). Their figures cannot be checked against a current source. They only matter for pricing old transcripts, where keeping them does no harm.

Opus 4.1, Opus 4, Sonnet 4 and Haiku 3.5 are retired on the Claude API but still carry published prices on the docs page, and the repo's figures for them match.

## How a session's cost is computed

A session is priced in `ledger/recorder.py` by `usage_and_cost` (line 314). It walks the session's transcript lines, keeps assistant messages with a model and a usage block, dedupes on `message.id`, and for each message calls `aggregate.usage_counts` (line 178) and `aggregate.message_cost` (line 87). The same two functions price the daily buckets in `aggregate.collect` and the rolling windows in `limits.scan`.

`usage_counts` reads five token classes from the API usage block: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and the cache write split by duration from `cache_creation.ephemeral_5m_input_tokens` and `cache_creation.ephemeral_1h_input_tokens`. `message_cost` multiplies each by its own rate and divides by a million: input at `input`, output at `output`, 5-minute writes at `cache_write_5m`, 1-hour writes at `cache_write_1h`, reads at `cache_read`. So yes: cache writes and cache reads are each counted at their own rates, the two write durations are priced separately, and for a priced model at standard speed the result is exactly token counts multiplied by the API list price.

I ran the repo's own `usage_and_cost` over this session's transcript, which Claude Code writes to `~/.claude/projects/` in the container. It returned 38 input, 8,464 output, 92,922 one-hour cache-write and 1,911,564 cache-read tokens, listed `claude-opus-5-5` under `unpriced_models`, and gave `cost_usd` 0.0. At the published Opus 5.5 rates the same counts cost $1.30.

It can differ from list price in these places, most serious first.

1. An unpriced model costs $0.00. `price_for` (aggregate.py line 80) returns nothing for `claude-opus-5-5`, and every message on it adds zero. `recorder.py` records the model in `unpriced_models` and `aggregate.py` prints a warning, but `limits.py` line 111 sets the cost to 0.0 with no warning at all. Any downstream figure built from `cost_usd` (gate priors, estimator samples, register totals) then carries the zero. The estimator's fit keeps only `claude-opus-5` runs with a cost above zero (estimate.py line 229), and the prior derivation skips runs whose `cost_usd` is zero (recorder.py line 652), so a run wholly on Opus 5.5 drops out of both. A run that mixes Opus 5.5 with a priced model is kept with only the priced part of its cost, and enters the gate's `samples_usd` too low.

2. Fast mode is not priced. The transcript's usage block carries `speed` (this session: `"standard"`), and the code never reads it. The docs page publishes fast mode at $8 input and $40 output for Opus 5.5, and $10 and $50 for Opus 5 and Opus 4.8, twice the standard rate, with cache multipliers applied on top. A fast-mode session is costed at half its list price.

3. Web search is not priced. The usage block carries `server_tool_use.web_search_requests`; the docs page charges $10 per 1,000 searches on top of tokens. The code never reads the field, so every search is missing $0.01. Web fetch has no extra charge, so it is correct to ignore.

4. US-only inference is not priced. The usage block carries `inference_geo` (this session: `"not_available"`). The docs page applies a 1.1x multiplier to every token class for Claude 4.6 and later models when it is `"us"`. The code applies no multiplier. For Claude Code sessions this is unlikely to bite; for scripted API runs that set it, cost is understated by 10 per cent.

5. Cache writes with no duration breakdown are priced at the 5-minute rate (aggregate.py line 187). The published 1-hour rate is 2x input against 1.25x for 5-minute, so if those writes were in fact 1-hour writes they are understated by 37.5 per cent. The note at `prices.json` line 6 says all observed writes on the owner's machine are 1-hour. Current transcripts carry the breakdown (this session's do), so the risk is confined to older ones. Separately, when the breakdown is present but the two fields sum to less than `cache_creation_input_tokens`, the difference is dropped without a warning (line 189).

6. The dedupe keeps the first line of each `message.id`. Claude Code writes one line per content block and repeats the usage. In this container (Claude Code 2.1.283) every repeat carried identical usage, and the top-level usage equalled the sum of its `iterations` entries on all 22 messages, so first-wins is correct here. A message with no `id` is not deduped and is counted once per line (aggregate.py line 237, recorder.py line 350).

7. Only one folder level is read. `iter_transcripts` globs `*/*.jsonl` (aggregate.py line 166). Claude Code keeps a folder named after each session beside its transcript; in this container it held only `ccr-tip.json`. If a Claude Code version writes sub-agent transcripts inside that folder, their tokens are not counted. No sub-agent ran in this session, so I could not confirm the layout.

8. Model IDs must match exactly after a trailing `-YYYYMMDD` is removed (`DATE_SUFFIX`, aggregate.py line 31). A Bedrock ID such as `anthropic.claude-opus-5-5` or a Google Cloud ID with an `@` date would be unpriced. This only matters if a transcript records a cloud-provider ID.

9. Batch pricing (50 per cent off) is not applied. Claude Code sessions do not use the Batch API, so this is correct for transcripts.

No long-context adjustment is needed today: the docs page says Claude 4.6 and later models and Mythos Preview bill the full 1M-token window at standard rates, and it publishes no long-context premium for any other model.
