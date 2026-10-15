#!/usr/bin/env python3
"""Serial, fresh-prompt benchmark of a Strata or gufo server. Run inside Strata's prepared environment.

Guarded copy of strata-uma-borrow-20261010/scripts/longprompt.py.  On this box a prompt that meets the kernel's page migration
(compaction) or direct reclaim reads 0.2-1.5 s slower (var4k/), so: before each request it waits until /proc/vmstat's migration
and direct-reclaim counters have stood still for --quiet-s; during each prompt it samples /proc/vmstat, and each row gets
"reclaim": the counter increments over [send, send + prompt_ms] and "flag" (pgmigrate_success > --migrate-max, or any
allocstall / compact_stall).  kswapd's scans are recorded and do not flag.  --prime N reads one N-token prompt first, labelled
prime-N, which is not a measurement (the first prompt after a start meets the start's compaction most often)."""
import argparse
import hashlib
import json
import statistics
import sys
import threading
import time
import urllib.request
from pathlib import Path


def get(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


VM_KEYS = ("pgmigrate_success", "compact_stall", "allocstall_normal", "allocstall_movable", "allocstall_dma32",
           "pgscan_kswapd", "pgscan_direct", "pswpin", "pswpout")
GUARD_KEYS = ("pgmigrate_success", "compact_stall", "allocstall_normal", "allocstall_movable", "allocstall_dma32")


def vmstat():
    out = {}
    with open("/proc/vmstat") as f:
        for line in f:
            k, v = line.split()
            if k in VM_KEYS:
                out[k] = int(v)
    return out


class Sampler:
    """/proc/vmstat every 0.25 s on a thread, kept as (time.time(), counters)."""
    def __init__(self):
        self.samples, self.stop = [], threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            self.samples.append((time.time(), vmstat()))
            self.stop.wait(0.25)

    def delta(self, t0, t1):
        before = max((s for s in self.samples if s[0] <= t0), key=lambda s: s[0], default=self.samples[0])[1]
        after = min((s for s in self.samples if s[0] >= t1), key=lambda s: s[0], default=self.samples[-1])[1]
        return {k: after.get(k, 0) - before.get(k, 0) for k in VM_KEYS}


def wait_quiet(quiet_s, max_s):
    """Seconds waited until the guard counters stood still for quiet_s (or max_s passed)."""
    t_start = time.monotonic()
    last, still_since = None, time.monotonic()
    while True:
        cur = tuple(vmstat().get(k, 0) for k in GUARD_KEYS)
        now = time.monotonic()
        if cur != last:
            last, still_since = cur, now
        if now - still_since >= quiet_s or now - t_start >= max_s:
            return round(now - t_start, 2)
        time.sleep(0.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/workspace/Strata"))
    parser.add_argument("--pack", type=Path, default=Path("/workspace/Strata-data/packs/iq2_xs"))
    parser.add_argument("--url", default="http://127.0.0.1:18080")
    parser.add_argument("--out", type=Path, default=Path("/workspace/results"))
    parser.add_argument("--targets", default="4096,32768,128000")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--tag", default="")
    parser.add_argument("--engine", choices=["strata", "gufo"], default="strata")   # gufo: timings from the usage chunk
    parser.add_argument("--model-name", default="strata")
    parser.add_argument("--prime", type=int, default=0)   # one discarded prompt of this size before the measured ones
    parser.add_argument("--quiet-s", type=float, default=3.0)
    parser.add_argument("--quiet-max-s", type=float, default=60.0)
    parser.add_argument("--migrate-max", type=int, default=50000)   # pages
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(args.root), str(args.root / "tools")]
    from strata_tokenizer import Tokenizer
    from serve.frontend import ChatTemplate, openai_to_messages
    directory = args.pack / "tokenizer"
    vocab = json.loads((directory / "vocab.json").read_text())
    tokens = [None] * len(vocab)
    for token, number in vocab.items():
        tokens[number] = token
    tokenizer = Tokenizer(tokens, (directory / "merges.txt").read_text().splitlines(),
                          json.loads((directory / "token_type.json").read_text()))
    template = ChatTemplate(directory / "chat_template.jinja")
    if args.engine == "strata":
        initial = get(args.url + "/v1/status")
        (args.out / "initial-status.json").write_text(json.dumps(initial, indent=2) + "\n")
    rows = []
    sampler = Sampler()

    def request(content, maximum=256):
        req = {"model": args.model_name, "messages": [{"role": "user", "content": content}],
               "temperature": 0, "reasoning_effort": "none", "max_tokens": maximum,
               "stream": True, "stream_options": {"include_usage": True}}
        if args.engine == "gufo":
            req["cache_prompt"] = False
        return req

    def count(req):
        messages, tools, kwargs = openai_to_messages(req)
        return len(tokenizer.encode(template.render(messages, tools, **kwargs), parse_special=True))

    def perform(label, req, expected=None):
        body = json.dumps(req).encode()
        (args.out / (label + "-request.json")).write_bytes(body + b"\n")
        waited = wait_quiet(args.quiet_s, args.quiet_max_s) if label != "warmup" else 0.0
        print("start", label, "tokens", expected, "quiet_wait_s", waited, flush=True)
        chunks, texts, first, finish = [], [], None, None
        sent = time.time()
        started = time.perf_counter()
        wire = urllib.request.Request(args.url + "/v1/chat/completions", data=body,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(wire, timeout=1800) as response:
            for line in response:
                if not line.startswith(b"data: "):
                    continue
                payload = line[6:].strip()
                if payload == b"[DONE]":
                    break
                chunk = json.loads(payload)
                chunks.append(chunk)
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    text = (delta.get("content") or "") + (delta.get("reasoning_content") or "")
                    if text:
                        first = first if first is not None else time.perf_counter() - started
                        texts.append(text)
                    finish = choice.get("finish_reason") or finish
        elapsed = time.perf_counter() - started
        usage = next((chunk["usage"] for chunk in reversed(chunks) if "usage" in chunk), {})
        if args.engine == "strata":
            engine = get(args.url + "/metrics")["requests"][0]
        else:   # the same fields, from gufo's llama.cpp-style timings
            timings = next(chunk["timings"] for chunk in reversed(chunks) if "timings" in chunk)
            engine = {"prompt_tokens": usage["prompt_tokens"], "reused": usage.get("cached_tokens", 0),
                      "prompt_ms": timings["prompt_ms"], "decode_ms": timings["predicted_ms"],
                      "engine_generated": usage["completion_tokens"], "timings": timings, "gufo": usage.get("gufo")}
        row = {"label": label, "expected_prompt_tokens": expected,
               "request_sha256": hashlib.sha256(body).hexdigest(),
               "client_ttft_s": first, "client_elapsed_s": elapsed, "finish_reason": finish,
               "usage": usage, "engine": engine, "text": "".join(texts)}
        d = sampler.delta(sent, sent + engine["prompt_ms"] / 1000)
        why = [k for k in GUARD_KEYS if k != "pgmigrate_success" and d[k] > 0]
        if d["pgmigrate_success"] > args.migrate_max:
            why.insert(0, "pgmigrate_success")
        row["reclaim"] = {**d, "quiet_wait_s": waited, "flag": bool(why), "why": why}
        if expected is not None and engine["prompt_tokens"] != expected:
            raise RuntimeError(f"token count mismatch: {expected} vs {engine['prompt_tokens']}")
        if not texts:
            raise RuntimeError(f"no text received for {label}")
        (args.out / (label + "-raw.json")).write_text(json.dumps({"chunks": chunks, "row": row}, indent=2) + "\n")
        rows.append(row)
        (args.out / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
        print("done", label, json.dumps({"ttft_s": first, "elapsed_s": elapsed, "engine": engine, "reclaim": row["reclaim"]}), flush=True)
        return row

    perform("warmup", request("Reply with exactly the word READY.", 16))
    # Each nonce occurs before the filler so previous long prompts cannot be reused.
    filler = "\n".join(f"def task_{i:05d}(value: int) -> int: return (value * {(i % 97) + 1} + {i}) % 100003"
                       for i in range(12000))
    ending = ("\n\nWrite a detailed explanation of the code above. Discuss deterministic integer transforms, "
              "modulo arithmetic, testing, naming, complexity, and maintainability. Write at least 600 words.")
    plan = ([("prime", args.prime, 1)] if args.prime else []) + \
        [("tokens", t, r) for t in map(int, args.targets.split(",")) for r in range(1, args.runs + 1)]
    for kind, target, run in plan:
        if True:
            prefix = f"Benchmark nonce: series-{target}-{kind}-trial-{run}{args.tag}.\nReview this synthetic Python module:\n"
            lo, hi = 0, len(filler)
            while lo < hi:
                middle = (lo + hi + 1) // 2
                if count(request(prefix + filler[:middle] + ending)) <= target:
                    lo = middle
                else:
                    hi = middle - 1
            req = request(prefix + filler[:lo] + ending)
            actual = count(req)
            if actual < target - 20 or actual > target:
                raise RuntimeError(f"could not construct target {target}: {actual}")
            perform(f"tokens-{target}-run-{run}" if kind == "tokens" else f"prime-{target}", req, actual)
    sampler.stop.set()
    measured = [row for row in rows if row["label"].startswith("tokens-")]
    groups = {}
    for target in map(int, args.targets.split(",")):
        subset = [r for r in measured if r["label"].startswith(f"tokens-{target}-")]
        values = {
            "prompt_tokens": [r["engine"]["prompt_tokens"] for r in subset],
            "cached_tokens": [r["engine"].get("reused", 0) for r in subset],
            "output_tokens": [r["engine"]["engine_generated"] for r in subset],
            "client_ttft_s": [r["client_ttft_s"] for r in subset],
            "client_elapsed_s": [r["client_elapsed_s"] for r in subset],
            "prefill_tok_s": [(r["engine"]["prompt_tokens"] - (r["engine"].get("reused") or 0)) / (r["engine"]["prompt_ms"] / 1000) for r in subset],
            "decode_tok_s": [r["engine"]["engine_generated"] / (r["engine"]["decode_ms"] / 1000) for r in subset],
        }
        groups[str(target)] = {key: {"median": statistics.median(v), "min": min(v), "max": max(v)}
                              for key, v in values.items()}
    (args.out / "summary.json").write_text(json.dumps(groups, indent=2) + "\n")
    print("summary", json.dumps(groups), flush=True)


if __name__ == "__main__":
    main()
