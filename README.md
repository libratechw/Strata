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
- `2020/`: #2020 (STRATA_PF_F16). Both arms run the branch's binary, `F-borrow` without and `F-borrow_on` with
  `STRATA_PF_F16=1`. `ab-q4kxl-head/` is of 77506be1 (the PR's code: its head differs only in a test comment and the doc text); `ab-q4kxl-earlier/` and `ab-iq4xs-earlier/` of an earlier
  head with the same kernels (before the K-quant alignment check and the test changes), as is `layer-earlier.txt`
  (`hip_prefill_fused_iq --no-ref --only=<pair> --chunks=16384`, STRATA_PF_F16=0 / 1, three rounds: the output bits hash and
  the layer time per line). `default-path-hash.txt`: the same tool's output hashes without the switch, 296b59d2 against
  77506be1. `f16-*-run.txt`: 77506be1's test with the switch (the K-quant pairs, then the default pairs). `kl/`: first-token KL
  (`klrun.py` per arm; R no switches, B the section-5 switches with STRATA_PF_SWITCH_MIN_T=0 and STRATA_PF_FUSED=1, plus
  STRATA_PF_FUSED_KQ=1 for UD-Q4_K_XL, C = B + STRATA_PF_F16=1), `summary.json` with each request's hash and value.
- `2019q/`: #2019 (STRATA_QPREP, after the attention gate was split off). Both arms run the branch's binary (d61666ed's
  code), `F-borrow` without and `F-borrow_on` with `STRATA_QPREP=1`. `extra/`: a local copy of `hip_prefill_q_prep` widened
  to 72 combinations (none / linear / YaRN scaling, the angle table on / off, MRoPE on / off, 1 / 65 / 513 tokens, start
  positions 0 / 8,190), its log and result, linked against the build that carried both fusions (the same `q_prep` code).
- `2019g/`: STRATA_ATTN_GATE (split off #2019). Both arms run the branch's binary (b496d3fb's code), `F-borrow` without and
  `F-borrow_on` with `STRATA_ATTN_GATE=1`. `default-path-hash.txt`: `hip_prompt_attn_wmma 32768 2048 3` without the switch,
  STRATA_PA_FAST=0 / 1, two rounds, the output hash per case, 296b59d2 against the build that carried both fusions (whose
  attention files are this branch's). `extra/`: a local copy of the gated check with an output row stride of 6,152 and the
  padding filled with a sentinel, and its log (its FAIL lines are the fast kernel against FP64, which it misses by design).
