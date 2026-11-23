"""Measure the same test suite before/after the additional pysupport unit tests.

Run from an environment with Moin and requirements.d/development.txt installed:
    python scripts/measure_coverage.py before
    python scripts/measure_coverage.py after
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    artifacts = root / "_test_artifacts" / "coverage"
    temp = artifacts / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(TEMP=str(temp), TMP=str(temp), PYTHONHASHSEED="0")
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

    data = artifacts / f"{args.phase}.coverage"
    command = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        f"--data-file={data}",
        "-m",
        "pytest",
        "src/moin",
        # This integration suite starts an HTTP server and crawls it with Scrapy.
        "--ignore=src/moin/cli/_tests/test_scrapy_crawl.py",
        f"--basetemp={artifacts / ('tmp-' + args.phase)}",
        f"--junitxml={artifacts / (args.phase + '.xml')}",
        "-q",
        "--tb=short",
    ]
    if args.phase == "before":
        command.append("--ignore=src/moin/utils/_tests/test_pysupport_extra.py")

    log_path = artifacts / f"{args.phase}.log"
    print(f"Running {args.phase} measurement. Log: {log_path}", flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)

    for report_args in [
        ["json", "-o", str(artifacts / f"{args.phase}.json")],
        ["html", "-d", str(artifacts / f"html-{args.phase}")],
    ]:
        subprocess.run(
            [sys.executable, "-m", "coverage", *report_args, f"--data-file={data}"], cwd=root, env=env, check=True
        )

    report = json.loads((artifacts / f"{args.phase}.json").read_text(encoding="utf-8"))
    module = next(
        value for key, value in report["files"].items() if key.replace("\\", "/").endswith("/utils/pysupport.py")
    )
    for label, summary in [("Project", report["totals"]), ("pysupport.py", module["summary"])]:
        lines = summary["covered_lines"]
        statements = summary["num_statements"]
        branches = summary["covered_branches"]
        total_branches = summary["num_branches"]
        print(
            f"{label}: lines {lines}/{statements} ({100 * lines / statements:.2f}%), "
            f"branches {branches}/{total_branches} ({100 * branches / total_branches:.2f}%)"
        )
    print("\n".join(log_path.read_text(encoding="utf-8").splitlines()[-12:]))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
