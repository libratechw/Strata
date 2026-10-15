# Measurement records for the gfx1151 pull requests (base 296b59d2)

Ryzen AI Max+ 395 (gfx1151, 128 GB), Linux, ROCm 7.14.1 (clang 23). Local paths in the records are replaced by
`<model dir ...>`, `<build>`, `<checkout of 296b59d2>` and `<run dir>`.

## The A/B runs (`<PR>/ab/`)

`scripts/ab-guard.py` starts a fresh `--serve` server per arm and round (`<arm>-r<round>-config.json`: the engine's
arguments; `-env.json`: the `STRATA_*` variables), alternates the arms' order every round and discards round 0. Its
client, `scripts/longprompt-guard.py`, sends one chat request of exactly N tokens per size (a fresh nonce before a synthetic
Python filler, reasoning off, temperature 0, 256 tokens out; the requests are `<arm>-r<round>/tokens-N-run-1-request.json`),
after a discarded prime request. It waits until the kernel's page migration and direct-reclaim counters stand still, and
flags a request that meets either during its prompt (`reclaim` in each row); a flagged round is dropped for both arms.

`<arm>-r<round>/results.json` holds each request's row: `engine.prompt_ms` and `engine.prompt_tokens` are the engine's own
timing of the prompt read (no model load, no decode), `usage.prompt_tokens_details.cached_tokens` the prompt-cache reuse
(0 throughout). `<arm>-r<round>-startup.txt` is the engine's start-up line naming the gfx1151 defaults it set.

`stats-N.txt` (`scripts/stats-ab.py <run> N`): per arm the median tok/s of the kept rounds and the median of the per-round
prompt_ms ratio with a 95% bootstrap interval; `pairs-N.txt` (`scripts/pairs-ab.py`): every round.

## Contents

- `2078/`: #2078 (STRATA_REFILL_PARTS). Arm `F-borrow` runs 296b59d2's binary, `F-borrow_pr` the branch's (9066c1f8, the
  same tree as the PR head), both with the same variables; the switch comes from gfx1151's table.
