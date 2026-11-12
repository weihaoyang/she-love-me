"""Deep-dive one person with she-love-me's engine.

Runs the existing statistics + sampling pipeline on the person's bundle, and
optionally renders she-love-me's HTML report if a romance analysis.json exists.

    python scripts/network_deepdive.py --person "某人"
    python scripts/network_deepdive.py --person "某人" --analysis path/to/analysis.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPTS = Path(__file__).resolve().parent


def load_graph(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_person(graph, needle):
    for person in graph["persons"]:
        if person.get("kind") != "person":
            continue
        if needle in (person.get("username"), person.get("name")):
            return person
    for person in graph["persons"]:
        if person.get("kind") == "person" and needle in (person.get("name") or ""):
            return person
    return None


def run(script, *args):
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                            cwd=SCRIPTS.parent, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"{script} 失败：{result.stderr or result.stdout}")
    return result.stdout


def safe_name(value):
    return "".join(ch for ch in value if ch not in '\\/:*?"<>|').strip()[:40] or "person"


def summarize(stats):
    def get(path, default=None):
        value = stats
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    return {
        "total_messages": get("basic.total_messages"),
        "my_messages": get("basic.my_messages"),
        "their_messages": get("basic.their_messages"),
        "my_avg_seconds": get("reply_speed.my_avg_seconds"),
        "their_avg_seconds": get("reply_speed.their_avg_seconds"),
        "symmetry_score": get("balance_calibration.symmetry_score"),
        "positive": get("positive_emotion_count"),
        "negative": get("negative_emotion_count"),
    }


def main():
    parser = argparse.ArgumentParser(description="用 she-love-me 引擎深潜一个人")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--person", required=True)
    parser.add_argument("--output-dir", default="reports/network/deep")
    parser.add_argument("--analysis", help="该联系人的 she-love-me analysis.json（可选）")
    parser.add_argument("--since", help="采样起始日期 YYYY-MM-DD")
    parser.add_argument("--contact-name", help="报告中的联系人名（默认用图里的名字）")
    args = parser.parse_args()

    graph = load_graph(args.graph)
    person = find_person(graph, args.person)
    if not person:
        raise SystemExit(f"找不到：{args.person}")
    bundle = person.get("bundle_path")
    if not bundle or not Path(bundle).exists():
        raise SystemExit("bundle 不存在；先运行 network_build.py")

    out_dir = Path(args.output_dir) / safe_name(person["name"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stats_path = out_dir / "stats.json"
    history_path = out_dir / "chat_history.txt"

    run("stats_analyzer.py", "--input", bundle, "--output", str(stats_path))
    history_args = ["--input", bundle, "--output", str(history_path)]
    if args.since:
        history_args += ["--since", args.since]
    run("build_chat_history.py", *history_args)

    report_path = None
    if args.analysis:
        report_path = out_dir / "report.html"
        run("generate_html_report.py", "--stats", str(stats_path),
            "--analysis", args.analysis, "--messages", bundle,
            "--contact", args.contact_name or person["name"],
            "--output", str(out_dir / "reports"))
        candidates = list((out_dir / "reports").glob("*.html"))
        if candidates:
            report_path = candidates[0]

    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    payload = {
        "status": "ok",
        "person": {"username": person["username"], "name": person["name"],
                   "role": (person.get("label") or {}).get("role", "")},
        "bundle": bundle,
        "stats": str(stats_path.resolve()),
        "chat_history": str(history_path.resolve()),
        "report": str(report_path.resolve()) if report_path else None,
        "summary": summarize(stats),
    }
    (out_dir / "deepdive.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
