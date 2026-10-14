# RTX 3060 12 GiB / Windows: Strata 0.1.43, Q2_0, IQ2_XS and IQ3_XXS

Historical 0.1.43 measurements. Start with the [0.1.44.1 calibrated report](../2026-10-14-community-rtx-3060-0144-calibrated/README.md) for the newer results and a comparison using these saved observations. The measurements below were not rerun or changed.

Measured on 2026-10-12. This report measures three GSQ-RCO quantizations under practical settings on one PC: fresh prompt and decode speed, conversation reuse, long-context recall, and an IQ2_XS 128K-context soak. It is a version-specific report, not a paired version-regression test. **No 0.1.41 engine was run.** The [long-context supplement](long-context/README.md) additionally attempts IQ3_XXS at 128K and all three models at the 262,144-token limit.

## Hardware and software

- NVIDIA GeForce RTX 3060, 12 GiB VRAM; 12th Gen Intel(R) Core(TM) i7-12700; 63.78 GiB installed physical RAM.
- Windows 11 Pro, build 26300; NVIDIA driver 617.42; official CUDA 13.0 Windows engine 0.1.43. Source/tag commit `7695859aa13afb248bdb4d36f9b2e95707db079d`.
- Model storage: NVMe SSD, Transcend TS2TMTE250S. GPU power, PCIe link, temperature and clocks are sampled in [telemetry.csv](telemetry.csv); background desktop applications were left running and were not controlled.
- Engine binary SHA-256: `223289044f377c97e982cdacddb2e17b5726f63a0439765e3fb3e2bcfdf78656`. Model revision and verified shard hashes: [model-provenance.json](model-provenance.json). Pack, tokenizer, Expert-profile and shared MTP hashes: [runtime-artifacts.json](runtime-artifacts.json).

Windows commit limit was 73.28 GiB throughout the sampled runs. Pagefile allocation observed after measurement was 9.50 GiB; system/pagefile settings were not changed. The 95% guard uses this commit limit, not physical RAM. [Memory environment](memory-environment.json).

## Configurations

| Quantization | Context limits tested | Expert placement |
|---|---|---|
| Q2_0 | 65,536 / 131,072 / 262,144 | full native Expert arena |
| IQ2_XS | 65,536 / 131,072 / 262,144 | full native Expert arena |
| IQ3_XXS | 65,536 / 131,072 / 262,144 | resident 16 GiB plus OS file cache; buffered reads |

INT8 KV, 32,768-token VRAM KV window, automatic expert-cache and prefill sizes, MTP `--spec 4 --spec-min-p 0.5`, existing shared draft subset. Thinking `xhigh`; temperature 1, top_p 0.95, top_k 20, min_p 0, presence penalty 0, repetition penalty 1. No vision, calibration, or experimental speed projection. [Core configs](configs/) and the additional stage configs in the [supplement](long-context/README.md) preserve launch arguments; `<STRATA>`, `<DATA>` and `<LOCAL_ROOT>` are redacted local paths.

All configurations reuse the same locally prepared MTP runtime: 512 Q2_0 routed draft experts and a 106,299-token shortlist, byte-identical to Strata v0.1.43's `data/draft_vocab.bin`. The runtime hashes and [identity record](mtp-identity.json) identify the actual tested artifacts. The draft was prepared before this run; its upstream BF16 checkpoint revision was not revalidated here.

Placements differ deliberately to fit this machine. The IQ3_XXS measurements therefore include its file/cache tier and are not an isolated quantization-only comparison. 64K/128K/262K label the configured limit, not the actual input size; actual prompt counts appear below.

The IQ3_XXS core results come from the final 16 GiB series using a 1.5 GiB / 15-second available-RAM guard and the original commit guard. It completed all nine speed requests and four conversation turns before a 50%-depth recall guard stop. Earlier placement trials, stopped requests and incomplete cases remain separate from the core results; their conditions and outcomes are summarized below.

## Method

The standalone [runner](community_bench_0143.py) builds synthetic Python-module prompts and counts the full chat template locally. Corresponding model requests have the same input, seed and sampling. There is one server per configuration, one short warmup plus one 4K warmup (128 output tokens each), and three measured repetitions; target order is ascending, descending, ascending. Expert cache state is retained. Fresh measurements require zero reused prompt tokens. Model loading and warmup are excluded from speed summaries.

Speed requests complete normally at an output cap of 512 tokens, including reasoning. No early stream disconnect is used. Engine prompt/decode times determine throughput; the streaming client measures first reasoning/answer-token time and whole-request latency. Actual generated counts are retained. Failed/stopped requests are excluded from successful medians and kept in [per-request.json](per-request.json).

Recall uses a 2,048-token output cap; conversation turns use 1,024. No request-duration deadline is imposed. Protection stops an owned run if Windows commit is at least 95% for 30 seconds. The primary suite and strict 16 GiB trial use available RAM below 3 GiB for 5 seconds; the final IQ3_XXS 16 GiB core repeat uses below 1.5 GiB for 15 seconds. These guards can affect whether a request completes but do not change model sampling or throughput calculations. Approximately one-second telemetry records system RAM/commit, summed owned-process-tree RSS, GPU sensors and system-wide disk I/O. These are sampled peaks, not allocation maxima or process-attributed physical disk reads.

## Fresh speed results

The original core completed 45/45 planned speed requests. The table also includes the separately recorded long-context supplement; its attempts, failures and retry placements are in [long-context results](long-context/summary.json). Values are medians (minimum–maximum), three planned repeats per row. PP/decode units are tok/s; TTFT is seconds. Counts separated by `/` are the individual successful runs.

| Model | Context limit | Expert placement | Series | Target input | Actual prompt tokens | Generated tokens | Successful/attempted | PP | Decode | TTFT |
|---|---:|---|---|---:|---|---|---|---|---|---|
| Q2_0 | 65,536 | native | core | 4,096 | 4095/4095/4095 | 512/512/512 | 3/3 | 915.8 (913.8–949.1) | 62.9 (59.8–64.5) | 4.54 (4.37–4.55) |
| Q2_0 | 65,536 | native | core | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 1036.3 (1031.8–1079.3) | 58.7 (57.8–59.2) | 31.69 (30.45–31.83) |
| Q2_0 | 65,536 | native | core | 60,000 | 60000/60000/60000 | 512/512/512 | 3/3 | 1001.8 (995.4–1011.0) | 55.2 (54.6–63.6) | 59.98 (59.43–60.36) |
| Q2_0 | 131,072 | native | core | 4,096 | 4096/4096/4096 | 512/512/512 | 3/3 | 906.4 (897.9–925.5) | 58.5 (57.0–60.0) | 4.58 (4.48–4.62) |
| Q2_0 | 131,072 | native | core | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 1017.6 (1010.9–1018.8) | 60.7 (57.6–62.8) | 32.28 (32.24–32.49) |
| Q2_0 | 131,072 | native | core | 120,000 | 120000/120000/120000 | 512/512/512 | 3/3 | 965.3 (961.3–966.5) | 53.9 (52.2–57.1) | 124.43 (124.29–124.96) |
| Q2_0 | 262,144 | native | long-context | 4,096 | 4096/4096/4096 | 512/512/512 | 3/3 | 895.6 (895.5–948.0) | 63.7 (49.0–64.5) | 4.64 (4.37–4.64) |
| Q2_0 | 262,144 | native | long-context | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 1013.3 (1006.8–1067.9) | 54.8 (54.7–59.3) | 32.42 (30.76–32.62) |
| Q2_0 | 262,144 | native | long-context | 120,000 | 120000/120000/120000 | 512/512/512 | 3/3 | 956.4 (944.4–971.9) | 54.2 (49.7–57.1) | 125.61 (123.60–127.20) |
| Q2_0 | 262,144 | native | long-context | 260,000 | 260000/260000/260000 | 512/512/512 | 3/3 | 877.3 (872.3–877.6) | 50.6 (47.8–50.8) | 296.58 (296.49–298.27) |
| IQ2_XS | 65,536 | native | core | 4,096 | 4095/4095/4095 | 512/512/512 | 3/3 | 851.9 (850.0–880.2) | 57.3 (55.2–60.5) | 4.87 (4.70–4.88) |
| IQ2_XS | 65,536 | native | core | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 971.6 (961.8–973.9) | 57.5 (55.0–59.1) | 33.80 (33.72–34.14) |
| IQ2_XS | 65,536 | native | core | 60,000 | 60000/60000/60000 | 512/512/512 | 3/3 | 945.3 (940.6–950.2) | 55.8 (53.5–57.2) | 63.56 (63.23–63.88) |
| IQ2_XS | 131,072 | native | core | 4,096 | 4096/4096/4096 | 512/512/512 | 3/3 | 845.8 (842.4–869.9) | 57.6 (52.2–66.6) | 4.90 (4.76–4.92) |
| IQ2_XS | 131,072 | native | core | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 965.2 (958.3–966.5) | 56.6 (56.6–56.6) | 34.03 (33.98–34.27) |
| IQ2_XS | 131,072 | native | core | 120,000 | 120000/120000/120000 | 512/512/512 | 3/3 | 917.2 (915.0–917.4) | 54.9 (53.1–56.4) | 130.96 (130.93–131.27) |
| IQ2_XS | 262,144 | native | long-context | 4,096 | 4096/4096/4096 | 512/512/512 | 3/3 | 829.5 (829.4–875.0) | 57.2 (56.1–58.3) | 5.00 (4.73–5.00) |
| IQ2_XS | 262,144 | native | long-context | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 952.4 (945.5–994.1) | 55.9 (52.6–59.7) | 34.48 (33.04–34.73) |
| IQ2_XS | 262,144 | native | long-context | 120,000 | 120000/120000/120000 | 512/512/512 | 3/3 | 896.3 (889.5–896.4) | 53.5 (52.7–54.6) | 134.00 (133.99–135.03) |
| IQ2_XS | 262,144 | native | long-context | 260,000 | 260000/260000/260000 | 512/512/512 | 3/3 | 826.3 (825.7–828.8) | 47.4 (47.1–48.7) | 314.85 (313.91–315.10) |
| IQ3_XXS | 65,536 | resident 16 GiB | core | 4,096 | 4095/4095/4095 | 512/512/512 | 3/3 | 725.4 (723.8–746.5) | 36.8 (35.1–36.9) | 5.71 (5.54–5.72) |
| IQ3_XXS | 65,536 | resident 16 GiB | core | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 937.7 (935.5–968.4) | 37.6 (33.5–38.7) | 35.03 (33.92–35.11) |
| IQ3_XXS | 65,536 | resident 16 GiB | core | 60,000 | 60000/60000/60000 | 512/512/512 | 3/3 | 902.6 (902.0–912.0) | 36.8 (36.0–37.6) | 66.57 (65.88–66.62) |
| IQ3_XXS | 131,072 | resident 16 GiB | long-context | 4,096 | 4096/4096/4096 | 512/512/512 | 3/3 | 693.5 (684.7–697.5) | 34.0 (31.3–36.7) | 5.96 (5.94–6.05) |
| IQ3_XXS | 131,072 | resident 16 GiB | long-context | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 903.9 (895.6–914.8) | 34.1 (33.9–37.1) | 36.33 (35.90–36.67) |
| IQ3_XXS | 131,072 | resident 16 GiB | long-context | 120,000 | 120000/120000/120000 | 512/512/512 | 3/3 | 862.1 (856.6–865.4) | 33.2 (32.2–34.0) | 139.33 (138.81–140.22) |
| IQ3_XXS | 262,144 | resident 16 GiB | long-context | 4,096 | 4096/4096/4096 | 512/512/512 | 3/3 | 689.1 (687.9–704.4) | 34.2 (33.4–34.6) | 6.01 (5.87–6.02) |
| IQ3_XXS | 262,144 | resident 16 GiB | long-context | 32,768 | 32768/32768/32768 | 512/512/512 | 3/3 | 895.4 (894.9–900.4) | 35.1 (33.9–35.4) | 36.68 (36.47–36.70) |
| IQ3_XXS | 262,144 | resident 16 GiB | long-context | 120,000 | 120000/120000/120000 | 512/512/512 | 3/3 | 854.7 (852.3–856.4) | 31.1 (30.6–33.7) | 140.53 (140.26–140.93) |
| IQ3_XXS | 262,144 | resident 16 GiB | long-context | 260,000 | 260000/260000/260000 | 512/512/512 | 3/3 | 795.1 (793.4–795.7) | 32.2 (31.3–33.5) | 327.21 (326.96–327.91) |

Whole-request latencies, draft acceptance, cache counters and per-request resource observations are in [requests.csv](requests.csv) and [per-request.json](per-request.json). Complete generated answers/reasoning are in [outputs.json](outputs.json), keyed by request number; raw `output_file` names are provenance labels rather than package paths. Engine timing lines and startup information are in [logs](logs/).

## IQ3_XXS placement results and post-reboot retries

The table includes only successful first speed repetitions and completed replays of previously interrupted targets. Initial trials and post-reboot retries are separate sessions; each retry starts a fresh server and replays the request prefix through its target. Prefix counts include warmups. Target input hashes match the interrupted requests. Regenerated conversation follow-ups can differ when preceding answers change; per-profile comparisons are retained with the [retry evidence](post-reboot-retry/README.md). These are not full-suite or soak reruns, and retry measurements are excluded from the core medians.

The initial 20 GiB buffered20 profile used a 3 GiB / 5-second available-RAM guard and stopped at a sampled minimum of 2.88 GiB during its 60K speed request. After that stop, the strict 16 GiB profile kept the 3 GiB guard and stopped on its third 32K speed repetition at 2.82 GiB. The final 16 GiB series relaxed only the RAM guard to 1.5 GiB / 15 seconds to continue, but its 50%-depth 60K recall later stopped at 1.37 GiB.

All three were protective RAM-guard stops, not engine OOM. The 20 GiB stop left six speed requests, four conversation turns and three recall cases unattempted; the strict 16 GiB stop left one speed request, four conversation turns and three recall cases unattempted. The relaxed series did not complete all three recall positions in one continuous run; the 50% and 90% positions were run with separate fresh servers.

Post-reboot retries retained each profile's resident budget and RAM guard. All runs kept the 95% / 30-second commit guard. OS cache and desktop load are uncontrolled, so the outcomes cannot be attributed to reboot alone.

| Run / placement | Case | Result | PP tok/s | Decode tok/s | Minimum available RAM GiB | Session peak commit % | System disk reads GiB |
|---|---|---|---:|---:|---:|---:|---:|
| Initial / buffered16-relaxed | Speed 4,096, rep 1 | completed (1/1) | 746.5 | 36.9 | 8.69 | 66.7 | 1.35 |
| Initial / buffered16-relaxed | Speed 32,768, rep 1 | completed (1/1) | 968.4 | 33.5 | 6.55 | 66.7 | 1.76 |
| Initial / buffered16-relaxed | Speed 60,000, rep 1 | completed (1/1) | 902.6 | 36.0 | 5.36 | 66.7 | 1.80 |
| Initial / buffered16-strict | Speed 4,096, rep 1 | completed (1/1) | 730.2 | 37.6 | 7.29 | 66.8 | 1.24 |
| Initial / buffered16-strict | Speed 32,768, rep 1 | completed (1/1) | 966.2 | 35.4 | 4.52 | 66.8 | 1.85 |
| Initial / buffered16-strict | Speed 60,000, rep 1 | completed (1/1) | 908.9 | 35.5 | 3.93 | 66.8 | 0.88 |
| Initial / buffered20 | Speed 4,096, rep 1 | completed (1/1) | 752.2 | 39.3 | 6.48 | 75.6 | 1.33 |
| Initial / buffered20 | Speed 32,768, rep 1 | completed (1/1) | 948.6 | 39.9 | 4.13 | 75.6 | 2.51 |
| After reboot / buffered20 | Speed 60,000, rep 1 target | completed (5/5 prefix) | 907.5 | 36.0 | 5.77 | 64.5 | — |
| After reboot / buffered16-strict | Speed 32,768, rep 3 target | completed (10/10 prefix) | 913.9 | 40.7 | 3.47 | 59.2 | — |
| After reboot / buffered16-relaxed | Recall, depth 50%, 60,000 input | found (17/17 prefix) | 876.3 | 34.9 | 3.67 | 59.4 | — |

Initial RAM minima are per-request sampled minima; retry minima cover the full replay profile, including load and warmups. Initial system disk-read values are whole-machine counter deltas, not model-attributed I/O or the engine's logical file-tier reads; retry rows leave that column blank while telemetry remains in the saved CSVs. Across the three post-reboot profiles, all 32 prefix requests completed under their original guards, and the 50%-depth recall retry found the expected word. The 500 MiB retry guard was not used. Attempts and outputs remain separate from the core speed and recall results; the [retry procedure, inputs and outputs](post-reboot-retry/README.md) preserve their provenance. Reducing startup headroom alone would not increase the explicit 20 GiB resident budget; the startup log confirms that the full budget was allocated.

## Conversation continuation

A roughly 32K module is acknowledged, then three turns add roughly 1,024 source tokens each. The actual previous assistant answers are included. This checks reuse and API continuity, not coding correctness. An empty answer at the output cap ends that sequence and is recorded explicitly.

| Session | Turn | Prompt tokens | Reused tokens | Fresh tokens | TTFT seconds |
|---|---:|---:|---:|---:|---:|
| q2_0-65536 | 0 | 32757 | 0 | 32757 | 32.11 |
| q2_0-65536 | 1 | 33822 | 32752 | 1070 | 2.12 |
| q2_0-65536 | 2 | 34918 | 33817 | 1101 | 2.12 |
| q2_0-65536 | 3 | 36010 | 34913 | 1097 | 2.11 |
| q2_0-131072 | 0 | 32757 | 0 | 32757 | 32.16 |
| q2_0-131072 | 1 | 33818 | 32752 | 1066 | 2.09 |
| q2_0-131072 | 2 | 34915 | 33813 | 1102 | 2.11 |
| q2_0-131072 | 3 | 36014 | 34910 | 1104 | 2.12 |
| iq2_xs-65536 | 0 | 32757 | 0 | 32757 | 34.01 |
| iq2_xs-65536 | 1 | 33820 | 32752 | 1068 | 2.28 |
| iq2_xs-65536 | 2 | 34905 | 33815 | 1090 | 2.28 |
| iq2_xs-65536 | 3 | 35994 | 34900 | 1094 | 2.29 |
| iq2_xs-131072 | 0 | 32757 | 0 | 32757 | 33.85 |
| iq2_xs-131072 | 1 | 33820 | 32752 | 1068 | 2.28 |
| iq2_xs-131072 | 2 | 34914 | 33815 | 1099 | 2.30 |
| iq2_xs-131072 | 3 | 36013 | 34909 | 1104 | 2.29 |
| iq3_xxs-65536-buffered16-relaxed | 0 | 32757 | 0 | 32757 | 35.10 |
| iq3_xxs-65536-buffered16-relaxed | 1 | 33820 | 32752 | 1068 | 3.56 |
| iq3_xxs-65536-buffered16-relaxed | 2 | 34907 | 33815 | 1092 | 3.66 |
| iq3_xxs-65536-buffered16-relaxed | 3 | 36001 | 34902 | 1099 | 3.64 |

## Original core recall

The original core places one known code word at 10%, 50% and 90% of each model's longest input in that core. Later 120K/260K recall tests are retained in the [long-context supplement](long-context/README.md). A pass means the expected word occurs in the final answer; reasoning alone does not count. 9/9 completed planned cases passed. IQ3_XXS's continuous 16 GiB relaxed session passed depth 10%, then crossed the 1.5 GiB / 15-second guard at depth 50%. That interrupted attempt is retained as `recall_trial`, outside this completed-case table. Depths 50% and 90% were tested with a fresh server and the same 16 GiB/relaxed guard, restarted separately for each depth. Those cases reset the server's Expert cache; the OS file cache was not explicitly cleared and its state was uncontrolled. These nine planned inputs do not establish general answer quality.

| Session | Needle depth | Actual prompt tokens | Result |
|---|---:|---:|---|
| q2_0-131072 | 10% | 120000 | found |
| q2_0-131072 | 50% | 120000 | found |
| q2_0-131072 | 90% | 120000 | found |
| iq2_xs-131072 | 10% | 120000 | found |
| iq2_xs-131072 | 50% | 120000 | found |
| iq2_xs-131072 | 90% | 120000 | found |
| iq3_xxs-65536-buffered16-relaxed | 10% | 60000 | found |
| iq3_xxs-65536-recall50-restarted | 50% | 60000 | found |
| iq3_xxs-65536-recall90-restarted | 90% | 60000 | found |

## IQ2_XS 128K continuous operation

Dedicated steady-state soak: 60.7 minutes, 56 back-to-back requests. Inputs cycle through 4K, 32K and 120K without artificial idle delays. Each input is fresh, with a unique tag and a 512-token generation cap. [Completion record](soak-completion.json).

Early/late columns describe the first/last third of elapsed soak time for the same target length. Different generated text and draft acceptance can change decode speed, so this is observational and not a controlled thermal-drift experiment.

| Target input | Successful requests | PP tok/s | Decode tok/s | Early decode tok/s | Late decode tok/s |
|---|---:|---|---|---|---|
| 4,096 | 19 | 846.5 (836.4–851.3) | 58.1 (50.2–62.0) | 58.7 (55.1–60.1) | 58.2 (50.2–62.0) |
| 32,768 | 19 | 971.6 (965.8–975.3) | 57.6 (51.3–59.7) | 57.7 (51.3–59.4) | 56.6 (52.3–58.4) |
| 120,000 | 18 | 916.6 (913.1–919.5) | 54.0 (48.6–57.8) | 54.2 (48.6–55.9) | 53.0 (51.0–57.8) |

## Sampled resource observations

These session-wide samples include loading, warmup and inference; the IQ2_XS 128K row also includes the soak. The restarted IQ3 recall labels split loading/warmup (`restarted`) from each depth's inference (`recall50-restarted`, `recall90-restarted`). RAM is system-wide used RAM, available RAM is its sampled minimum, commit is the peak fraction of the Windows commit limit, and VRAM is total GPU usage including the desktop. Units are GiB, %, and °C.

| Session | Peak RAM GiB | Minimum available RAM GiB | Peak commit % | Peak VRAM GiB | Peak GPU °C |
|---|---:|---:|---:|---:|---:|
| q2_0-65536 | 49.6 | 14.2 | 89.8 | 11.1 | 89.0 |
| q2_0-131072 | 49.8 | 14.0 | 91.3 | 11.1 | 90.0 |
| iq2_xs-65536 | 50.2 | 13.5 | 91.9 | 11.1 | 89.0 |
| iq2_xs-131072 | 51.7 | 12.1 | 94.4 | 11.1 | 90.0 |
| iq3_xxs-65536-buffered16-relaxed | 62.4 | 1.4 | 66.7 | 11.1 | 90.0 |
| iq3_xxs-65536-buffered16-strict | 61.0 | 2.8 | 66.8 | 11.1 | 89.0 |
| iq3_xxs-65536-buffered20 | 60.9 | 2.9 | 75.6 | 11.1 | 89.0 |
| iq3_xxs-65536-recall50-restarted | 55.0 | 8.8 | 66.4 | 11.1 | 89.0 |
| iq3_xxs-65536-recall90-restarted | 54.9 | 8.8 | 66.6 | 11.1 | 90.0 |
| iq3_xxs-65536-restarted | 52.4 | 11.4 | 66.1 | 11.1 | 79.0 |

## Historical observations and limitations

The separately retained short-sample history contains two 0.1.41 and two 0.1.43 64K-context runs on the same roughly 4K input. Median decode was 41.4 versus 58.2 tok/s, and PP 866.0 versus 892.9 tok/s. Those requests were intentionally disconnected around 256 generated tokens, so they are **not part of the completed-request tables above**. The measurements are on different days, and preparation differed (old: non-thinking/temperature 0; new: thinking/temperature 1). They do not isolate an update's effect. No old engine was rerun. [Retained historical samples](historical-short-samples.json).

This report does not test contexts beyond 262,144, every memory/cache/KV/MTP tuning combination, parallel clients, images, or ts-bench/HumanEval answer quality. It is one Windows PC with uncontrolled desktop background load. Failed/stopped cases and incomplete conversation sequences remain in the package. No system settings or daily IQ2_XS configuration were changed, and the owned server was stopped after measurement.

## Reproduce

Install the official Strata 0.1.43 Windows CUDA engine and its pinned Python dependencies. Obtain the three GGUF pairs at the revision in model-provenance.json, verify their published SHA-256, and build native packs with `tools/iq_pack.py --gguf FIRST_SHARD --out PACK_DIR`. For exact MTP conditions, reuse an `rt` folder matching runtime-artifacts.json and mtp-identity.json; a different draft runtime or shortlist changes the comparison. The supplied runner does not prepare MTP files. No Expert repack is required on this AVX2 CPU.

From the installed environment, choose a new empty output directory:

```text
.venv\Scripts\python.exe community_bench_0143.py --runtime PATH_TO_STRATA --data PATH_TO_STRATA_DATA --out NEW_OUTPUT_DIR --soak-seconds 3600
.venv\Scripts\python.exe iq3_buffered16_strict.py --runner community_bench_0143.py --runtime PATH_TO_STRATA --data PATH_TO_STRATA_DATA --out NEW_STRICT_IQ3_OUTPUT_DIR
.venv\Scripts\python.exe iq3_buffered16_supplement.py --runner community_bench_0143_relaxed.py --runtime PATH_TO_STRATA --data PATH_TO_STRATA_DATA --out NEW_IQ3_OUTPUT_DIR
.venv\Scripts\python.exe iq3_recall_restart.py --runner community_bench_0143_relaxed.py --runtime PATH_TO_STRATA --data PATH_TO_STRATA_DATA --out NEW_RECALL_OUTPUT_DIR
.venv\Scripts\python.exe merge_community_0143.py --primary NEW_OUTPUT_DIR --strict NEW_STRICT_IQ3_OUTPUT_DIR --relaxed NEW_IQ3_OUTPUT_DIR --recall NEW_RECALL_OUTPUT_DIR --out NEW_MERGED_DIR
.venv\Scripts\python.exe analyze_community_0143.py NEW_MERGED_DIR --out NEW_ANALYSIS_DIR
```

The [merge script](merge_community_0143.py) combines all four raw `rows.jsonl` / `telemetry.jsonl` series before analysis. Q2_0 and IQ2_XS core results come from the primary series. IQ3_XXS core speed, conversation and depth-10 recall come from the relaxed 16 GiB series; depth-50/90 recall comes from the fresh-server series. Earlier IQ3 speed series become `placement_trial`; earlier IQ3 conversations and recall attempts, including any that complete on a new machine, remain separate trial groups. The merge renumbers requests and identifies each source series/session. It writes metrics only; output filenames are provenance labels, and generated outputs remain in the original measurement directories. New measurements may complete a different number of requests or have different speeds.

To regenerate the retained report's machine-readable tables without inference, use the packaged `per-request.json` and `telemetry.csv` directly:

```text
python analyze_community_0143.py PATH_TO_THIS_REPORT_FOLDER --out NEW_RETAINED_ANALYSIS_DIR
```

The analysis writes `summary.json`, `enriched-requests.json` and `requests.csv` to a new directory and leaves its input unchanged. `summary.json` contains speed, recall, conversation, soak and resource tables; its retained-data values can be compared directly with the published [summary](summary.json). Post-reboot prefix retries remain separate and are not merged into these core tables. Both retained-input and four-raw-series aggregation were checked against the complete published summary without inference; raw local-path redactions were normalized for that comparison. [Aggregation validation](aggregation-validation.json).

The runner never downloads models, updates an engine, runs an old engine, edits daily configs, or changes system settings. It requires an unused localhost port 18080 and stops only its own processes. Core context, ordering, caps, protection thresholds and placement are frozen in [protocol.json](protocol.json); the additional tests use their own [protocol](long-context/protocol.json). Timing fields ending in `_ms` are milliseconds; `_s` and `_seconds` timing fields are seconds. Throughput fields are tokens/second, and memory byte fields are bytes. Resource medians/min/max are observed samples. Large model files, duplicate long input text and raw download logs are omitted from this report package; the runner deterministically regenerates the input text.

Check the original core's request contracts and matching-input hashes without running inference; the additional [validator and procedure](long-context/README.md) cover the long-context supplement:

```text
python validate_community_0143.py PATH_TO_THIS_REPORT_FOLDER
```

## Additional long-context attempts

See the [supplement](long-context/README.md) for complete attempts/unattempted cases, retry placement, guards and sampled resource observations. The original 45-request core and its 1-hour soak are unchanged; the combined speed table reads the two independently retained summaries. Speed uses three planned repetitions at each input length; recall uses three positions at the longest input. Q2_0 completed before a user-requested pause; the remaining models resumed afterwards. No old engine or Q2_0 retest was run. Background load and OS cache remain uncontrolled.

All four additional profiles completed under the primary 1 GiB / 15-second available-RAM guard. Neither the 500 MiB retry nor a reduced-residency fallback was needed. The commit guard stayed at 95% / 30 seconds.

| Model / context / placement | Stage | RAM floor MiB | Recall depth | Actual input tokens | Completed | Code word in final answer |
|---|---|---:|---:|---:|---|---|
| q2_0-262144-native | stage0 | 1024 | 10% | 260000 | True | True |
| q2_0-262144-native | stage0 | 1024 | 50% | 260000 | True | True |
| q2_0-262144-native | stage0 | 1024 | 90% | 260000 | True | True |
| iq2_xs-262144-native | stage0 | 1024 | 10% | 260000 | True | True |
| iq2_xs-262144-native | stage0 | 1024 | 50% | 260000 | True | True |
| iq2_xs-262144-native | stage0 | 1024 | 90% | 260000 | True | True |
| iq3_xxs-131072-resident16 | stage0 | 1024 | 10% | 120000 | True | True |
| iq3_xxs-131072-resident16 | stage0 | 1024 | 50% | 120000 | True | True |
| iq3_xxs-131072-resident16 | stage0 | 1024 | 90% | 120000 | True | True |
| iq3_xxs-262144-resident16 | stage0 | 1024 | 10% | 260000 | True | True |
| iq3_xxs-262144-resident16 | stage0 | 1024 | 50% | 260000 | True | True |
| iq3_xxs-262144-resident16 | stage0 | 1024 | 90% | 260000 | True | True |

Whole-session sampled memory includes loading and warmups.

| Model / context / placement | Minimum available RAM GiB | Peak commit % | Peak VRAM GiB |
|---|---:|---:|---:|
| q2_0-262144-native | 15.02 | 86.18 | 11.15 |
| iq2_xs-262144-native | 15.30 | 85.66 | 11.19 |
| iq3_xxs-131072-resident16 | 2.99 | 61.80 | 11.17 |
| iq3_xxs-262144-resident16 | 1.00 | 64.29 | 11.40 |

Every stage outcome, including load/warmup failures and remaining cases, is retained below. Request counts and sampled memory include loading/warmups. Telemetry source_stage identifies each launch.

| Stage | Expert placement | Available-RAM floor MiB / seconds | Successful / attempted requests | Minimum available RAM GiB | Peak commit % | Stop/error | Unfinished cases after stage |
|---|---|---|---:|---:|---:|---|---:|
| q2_0-262144-stage0 | native | 1024 / 15 | 17 / 17 | 15.02 | 86.18 | none | 0 |
| iq2_xs-262144-stage0 | native | 1024 / 15 | 17 / 17 | 15.30 | 85.66 | none | 0 |
| iq3_xxs-131072-stage0 | resident 16 GiB | 1024 / 15 | 14 / 14 | 2.99 | 61.80 | none | 0 |
| iq3_xxs-262144-stage0 | resident 16 GiB | 1024 / 15 | 17 / 17 | 1.00 | 64.29 | none | 0 |
