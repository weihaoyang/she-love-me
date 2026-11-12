"""One-command pipeline: graph → intimacy → analysis → report → weekly → profiles.

    python scripts/network_pipeline.py --input data/contacts --top 10
    python scripts/network_pipeline.py --deep 3      # 额外深潜前 3 个亲密候选
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(script, *args):
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise SystemExit(f"{script} 失败：\n{result.stderr or result.stdout}")
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {"raw": result.stdout.strip()}


def main():
    parser = argparse.ArgumentParser(description="一键跑完人脉分析全流程")
    parser.add_argument("--input", default="data/contacts")
    parser.add_argument("--names", default="data/network/names.json")
    parser.add_argument("--rooms", default="data/network/rooms.json")
    parser.add_argument("--labels", default="data/network/labels.json")
    parser.add_argument("--output", default="data/network")
    parser.add_argument("--reports", default="reports/network")
    parser.add_argument("--me")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--deep", type=int, default=0)
    parser.add_argument("--refresh-analysis", action="store_true")
    args = parser.parse_args()

    graph_path = Path(args.output) / "graph.json"
    analysis_path = Path(args.output) / "analysis.json"
    intimacy_path = Path(args.output) / "intimacy.json"
    report_path = Path(args.reports) / "dashboard.html"

    steps = {}

    build_args = ["--input", args.input, "--output", args.output]
    for flag, value in (("--names", args.names), ("--rooms", args.rooms),
                        ("--labels", args.labels), ("--me", args.me),
                        ("--since", args.since), ("--until", args.until)):
        if value:
            build_args += [flag, str(value)]
    steps["build"] = run("network_build.py", *build_args)

    steps["intimacy"] = run("network_intimacy.py", "--graph", str(graph_path),
                            "--output", str(intimacy_path))

    if not analysis_path.exists() or args.refresh_analysis:
        steps["analyze"] = run("network_analyze.py", "--graph", str(graph_path),
                               "--output", str(analysis_path), "--force", "--top", str(args.top))
    else:
        steps["analyze"] = {"status": "skipped", "reason": "analysis.json 已存在（避免覆盖人工改写）"}

    if args.deep:
        payload = json.loads(intimacy_path.read_text(encoding="utf-8"))
        names = [c["name"] for c in payload.get("candidates", [])[: args.deep]]
        deep = []
        for name in names:
            deep.append(run("network_deepdive.py", "--person", name,
                            "--output-dir", str(Path(args.reports) / "deep")))
        steps["deep"] = deep

    report_args = ["--graph", str(graph_path), "--output", str(report_path)]
    if analysis_path.exists():
        report_args += ["--analysis", str(analysis_path)]
    steps["report"] = run("network_report.py", *report_args)

    steps["weekly"] = run("network_weekly.py", "--graph", str(graph_path),
                          "--output", str(Path(args.reports) / "weekly.md"))

    profile_args = ["--graph", str(graph_path), "--top", str(args.top),
                    "--output", str(Path(args.reports) / "people")]
    if analysis_path.exists():
        profile_args += ["--analysis", str(analysis_path)]
    steps["profiles"] = run("network_person.py", *profile_args)

    print(json.dumps({
        "status": "ok",
        "dashboard": str(report_path.resolve()),
        "weekly": str((Path(args.reports) / "weekly.md").resolve()),
        "persons": steps["build"].get("persons"),
        "debt": steps["build"].get("debt"),
        "intimacy_candidates": steps["intimacy"].get("candidates"),
        "steps": list(steps),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
