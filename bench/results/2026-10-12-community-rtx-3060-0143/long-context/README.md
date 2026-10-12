# Long-context supplement, Strata 0.1.43

Extends the parent report to Q2_0 and IQ2_XS at a 262,144-token limit, and IQ3_XXS at 131,072/262,144. Speed inputs are 4,096, 32,768 and 120,000 tokens, plus 260,000 at the largest limit, with three planned repeats each in ascending/descending/ascending order. Recall tests put a code word at depths 10/50/90 of the longest input. A pass requires it in the final answer. Speed caps are 512 and recall caps 2,048, including reasoning. Sampling, xhigh thinking, MTP, INT8 KV and the 32,768-token resident KV window follow the parent protocol. No additional soak or old engine run is included.

The primary RAM guard is available RAM below 1 GiB for 15 seconds; resource-stopped cases may retry below 500 MiB for 15 seconds. Commit protection stays at 95% for 30 seconds. Only unfinished cases retry, with a fresh server and new warmups. Native Q2/IQ2 and 16 GiB IQ3 are tried first; a further fallback uses 24 GiB Q2/IQ2 or 12 GiB IQ3 residency with buffered file reads. Different placements stay in separate speed-table rows. Guard changes within the same placement retain every attempt; successful medians exclude failures. A new server resets its Expert cache, while OS cache and desktop load are uncontrolled.

[Per-request data](per-request.json), [generated outputs](outputs.json), [sampled telemetry](telemetry.csv), [summary](summary.json), [completion](completion.json) and [validation](validation.json) retain successes, failures and unattempted cases. Each stage subfolder includes configs, startup/timing logs published as .txt, cleanup and its frozen runner. Raw .log path references are provenance labels. The wrapper overrides resident launches to `STRATA_RESIDENT_HEADROOM_GIB=1` and `STRATA_UNBUFFERED_LOAD=0`; the underlying runner's environment JSON is written before that override. The launch wrapper and recorded resident budget identify the actual conditions. `output_file` is a provenance label, resolved through outputs.json by request number, not a packaged file path.

On the parent report's pinned Windows installation and model/MTP files, repeat using a new output directory:

```text
PATH_TO_VENV_PYTHON long_context_0143.py --runtime PATH_TO_STRATA --data PATH_TO_STRATA_DATA --runner PATH_TO_PARENT_REPORT/community_bench_0143.py --out NEW_LONG_OUTPUT_DIR
python PATH_TO_PARENT_REPORT/aggregate_long_context_0143.py --sources NEW_LONG_OUTPUT_DIR --out NEW_COMBINED_METRICS_DIR
python PATH_TO_PARENT_REPORT/analyze_community_0143.py NEW_COMBINED_METRICS_DIR --out NEW_ANALYSIS_DIR
```

To aggregate this retained supplement without inference or input changes:

```text
python PATH_TO_PARENT_REPORT/analyze_community_0143.py PATH_TO_THIS_SUPPLEMENT --out NEW_ANALYSIS_DIR
```

Session suffixes identify native or resident placement; source_stage and available_floor_mib record each request's actual launch and guard. Times, throughput and telemetry units follow the parent report. Loading and warmups are excluded from throughput, but included in whole-session memory peaks. These measurements establish completion on these inputs, not general long-context answer quality or daily-use stability.

Check retained input hashes across models, output-based recall, successful timing statistics, loaded engine/context/arena size, launch environment and cleanup without inference:

```text
python PATH_TO_PARENT_REPORT/validate_long_context_0143.py PATH_TO_PARENT_REPORT
```

The validator writes `measurement-contract-validation.json` in this supplement; it does not run a model.

The recorded run was split by a user-requested pause after Q2_0. `measured_initial.py` and `measured_resumed.py` retain the wrappers used for each part; `source-protocols.json` and `source-completions.json` identify those two parts. The portable long_context_0143.py supports `--profiles` to select remaining conditions into a new raw directory. The collector accepts multiple `--sources` to combine split runs. It retains every attempt and separates changed resident budgets; generated output files stay in their raw stage directories. No model was rerun solely to join the records.
