# Data: short GPU stalls while the kernel compacts memory (gfx1151)

The data behind the `docs/AMD_HIP.md` section "Linux: short stalls while the kernel compacts memory (speed measurements)".
This branch holds data only and shares no history with the code.

Machine: Ryzen AI Max+ 395 (gfx1151, 128 GB), ROCm 7.14.1, Linux 7.0, UD-IQ4_XS with the experts read from the GGUF in place.

`python3 scripts/summarize.py` recomputes the section's numbers from `runs/start-up` and `summary/later-prompts-requests.csv`.

## Start-up runs (`runs/start-up`)

A fresh engine per run (the repository at 7695859a with #2299 switched off; the command line is in each `config.json`), a short
warm-up, then two 4K prompts, each with its own nonce and read in full. The label names the setting:

| label | setting | runs |
|---|---|---:|
| `vm`, `kfd` | none (the defaults); the `kfd` runs also had the root KFD event reader | 10, 20 |
| `pinxfer` | `GPU_PINNED_MIN_XFER_SIZE=1048576` in the engine's environment | 10 |
| `nouserptr` | `HSA_USERPTR_FOR_PAGED_MEM=0` in the engine's environment | 10 |
| `nocomp` | `sysctl vm.compaction_proactiveness=0 vm.watermark_boost_factor=0` (set back to 20 and 15000 afterwards) | 10 |

Each run directory has `client.log` (request timings, `prompt_ms`), `procvm.log` (`/proc/vmstat`, a `T <unix time>` line per
sample, every 0.5 s), `engine.log`, `server.log`, `config.json` and `res/` (results). `kfd-root.log` is the output of
`scripts/kfd-events.py`, run as root during the `kfd` runs: the KFD SMI events of all processes (`QUEUE_EVICTION` lines are
`ns -pid node trigger`, trigger 0 SVM, 1 USERPTR). `smi-event.log` in each run is a non-root `amd-smi event`, which did not get
the engine's events; `summary/amd-smi-root.txt` is the error amd-smi 27.1.0 gave as root.

The runs were made by `scripts/delay4k3.sh` (and `scripts/workaround4k.sh` for `pinxfer` and `nouserptr`).

## A/B runs

Whole-prompt A/B of `STRATA_GDN_CHUNKED` off / on (#2299), made by `scripts/ab-guard.py`. Configurations: F = the switches of
`docs/STRIX_HALO.md` section 5, D = the defaults. Arm labels read `<F|D>-borrow@off|on`; `borrow` is only the runner's arm name.

| directory | engine | what it gives |
|---|---|---|
| `runs/ab-4k` | 7695859a with #2299 | the 11-pair 4K A/B whose first / second prompt intervals the PR quotes (`summary/ab-4k-*`) |
| `runs/ab-a0116b27` | a0116b27 with #2299 | the "later prompts" row: 4K / 32K / 128K, a discarded 4K prompt first on each engine (`summary/later-prompts-requests.csv`) |
| `runs/ab-296b59d2` | 296b59d2 with #2299 | the same kind of A/B on 296b59d2, measured with the section's steps (`summary/current-main-requests.csv`) |

## Summaries (`summary`)

| file | what it is |
|---|---|
| `per-start-counters.txt` | each start-up run: `prompt_ms` and `/proc/vmstat` increments of both prompts |
| `first-vs-second.txt` | the `prompt_ms` pairs with d = first - second |
| `kfd-evictions.txt` | the `kfd` runs per prompt: page migration, the engine's evictions by trigger and the time evicted (from `scripts/kfd-window.py`) |
| `prefill-timing.txt` | `STRATA_PREFILL_TIMING=1` phase times of slow and normal first prompts |
| `later-prompts-requests.csv`, `current-main-requests.csv` | every request of the two A/Bs with its `/proc/vmstat` increments and the runner's flag |
| `ab-4k-pairs.csv`, `ab-4k-stats.txt` | the 4K A/B pairs and the bootstrap statistics |
