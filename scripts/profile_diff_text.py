"""Profile and benchmark original and working-tree text diff implementations.

Run: python scripts/profile_diff_text.py --baseline 537e36b0
Outputs are written under _test_artifacts/profiling (ignored by Git).
"""

import argparse
import cProfile
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import pstats
import statistics
import subprocess
import sys
import time
import timeit

from moin.utils import diff_text


def scenarios():
    for size in (100, 5000):
        text = "".join(f"Wiki line {i:05d}: stable content with [[Page{i % 20}]].\n" for i in range(size))
        # Split separately, as two independently loaded revisions would be.
        yield f"unchanged_{size}", text.splitlines(), text.splitlines()
        if size == 5000:
            edited = text.splitlines()
            edited[size // 2] = "Changed wiki paragraph with different content."
            yield "edited_5000", text.splitlines(), edited


def run_calls(function, oldlines, newlines, count):
    for _ in range(count):
        function(oldlines, newlines)


def profile(function, oldlines, newlines, destination):
    profiler = cProfile.Profile()
    profiler.runcall(run_calls, function, oldlines, newlines, 30)
    profiler.dump_stats(str(destination.with_suffix(".prof")))
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.strip_dirs().sort_stats("cumulative").print_stats(20)
    destination.with_suffix(".txt").write_text(stream.getvalue(), encoding="utf-8")
    return {"iterations": 30, "function_calls": stats.total_calls, "profiled_seconds": stats.total_tt}


def benchmark(functions, oldlines, newlines, repeats):
    timers = {}
    iterations = {}
    samples = {name: [] for name in functions}
    expected = functions["before"](oldlines, newlines)
    for name, function in functions.items():
        for _ in range(3):
            assert function(oldlines, newlines) == expected, f"Output mismatch: {name}"
        timers[name] = timeit.Timer(lambda function=function: function(oldlines, newlines))
        # Each measured batch lasts approximately >= 0.2 s during calibration.
        iterations[name], _ = timers[name].autorange()

    for repeat in range(repeats):
        # Alternate order to reduce systematic bias from machine load/drift.
        order = list(functions) if repeat % 2 == 0 else list(reversed(functions))
        for name in order:
            elapsed = timers[name].timeit(number=iterations[name])
            samples[name].append(elapsed / iterations[name])

    result = {}
    for name in functions:
        values = samples[name]
        result[name] = {
            "iterations_per_sample": iterations[name],
            "samples_seconds_per_call": values,
            "median_seconds_per_call": statistics.median(values),
            "min_seconds_per_call": min(values),
            "max_seconds_per_call": max(values),
        }
    result["speedup"] = result["before"]["median_seconds_per_call"] / result["after"]["median_seconds_per_call"]
    result["output_sha256"] = hashlib.sha256(repr(expected).encode("utf-8")).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="HEAD", help="Git revision containing the original implementation")
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error("--repeats must be at least 3")

    root = Path(__file__).resolve().parents[1]
    output = root / "_test_artifacts" / "profiling"
    output.mkdir(parents=True, exist_ok=True)
    source_path = "src/moin/utils/diff_text.py"
    baseline = subprocess.check_output(["git", "rev-parse", "--verify", args.baseline], cwd=root, text=True).strip()
    original = subprocess.check_output(["git", "show", f"{baseline}:{source_path}"], cwd=root)
    snapshot = output / "baseline_diff_text.py"
    snapshot.write_bytes(original)
    spec = importlib.util.spec_from_file_location("baseline_diff_text", snapshot)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    functions = {"before": module.diff, "after": diff_text.diff}

    clock = time.get_clock_info("perf_counter")
    results = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": baseline,
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "repeats": args.repeats,
        "timer": {"implementation": clock.implementation, "resolution_seconds": clock.resolution},
        "baseline_sha256": hashlib.sha256(original).hexdigest(),
        "working_sha256": hashlib.sha256((root / source_path).read_bytes()).hexdigest(),
        "scenarios": {},
    }
    for name, oldlines, newlines in scenarios():
        result = benchmark(functions, oldlines, newlines, args.repeats)
        result["profiles"] = {
            variant: profile(function, oldlines, newlines, output / f"{name}-{variant}")
            for variant, function in functions.items()
        }
        results["scenarios"][name] = result
        before = result["before"]["median_seconds_per_call"] * 1000
        after = result["after"]["median_seconds_per_call"] * 1000
        print(f"{name}: {before:.6f} -> {after:.6f} ms/call; speedup {result['speedup']:.2f}x", flush=True)

    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {output / 'results.json'}")


if __name__ == "__main__":
    main()
