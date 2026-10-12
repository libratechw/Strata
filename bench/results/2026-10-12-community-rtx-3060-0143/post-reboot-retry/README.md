# Post-reboot request-prefix retries

The original three interrupted requests were retried with their original RAM guards. Each profile starts a fresh server, retains cache within that profile, and ends after the original interrupted target. The OS file cache is not explicitly cleared. Core speed medians in the parent report are unchanged.

`measured_retry.py` is the exact script used, with its raw-evidence directory layout. Its final all-inputs-match assertion reported a mismatch after measurement because conversation answers changed. Recorded requests and cleanup are intact; completion/comparison metadata was finalized separately. `retry_post_reboot_0143.py` adapts the input loader to the packaged parent report's merged `per-request.json` and frozen runners, and records conversation-history differences separately while requiring fresh-input hashes to match. To repeat on an installed Strata 0.1.43 environment with the same model packs and MTP runtime:

```text
PATH_TO_VENV_PYTHON retry_post_reboot_0143.py --runtime PATH_TO_STRATA --data PATH_TO_STRATA_DATA --original PATH_TO_PARENT_REPORT_FOLDER --out NEW_EMPTY_RETRY_DIR
```

The source request hashes are retained in each profile's input-comparison.json. Conversation follow-ups include the model's newly generated preceding answers, so matching every follow-up is checked rather than assumed. The frozen runner snapshots identify the actual guards used. Timing and memory units follow the parent report; profile telemetry is sampled at approximately one-second intervals. `outcome.json` contains the before-load sample and target result, while `summary.json` compares each previously stopped target with its retry.
