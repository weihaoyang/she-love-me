"""Weekly action list: the three to six messages that actually matter.

    python scripts/network_weekly.py --graph data/network/graph.json --limit 6
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import network_metrics as nm  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def render(actions, today=None, limit=6):
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# 本周人脉行动清单 · {today}", ""]
    if not actions:
        lines.append("没有需要处理的行动。")
        return "\n".join(lines)
    for index, action in enumerate(actions[:limit], 1):
        lines.append(f"**{index}. {action['name']}（{action['type']}，{action['days']} 天）**")
        lines.append(f"- 为什么：{action['reason']}")
        lines.append(f"- 做什么：{action['action']}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成本周人脉行动清单")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--output", help="写入 Markdown 文件")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    persons = [p for p in graph["persons"] if p.get("kind") == "person"]
    actions = nm.weekly_actions(persons, limit=args.limit)

    if args.json:
        print(json.dumps(actions, ensure_ascii=False, indent=1))
        return
    text = render(actions, limit=args.limit)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(json.dumps({"status": "ok", "output": str(Path(args.output).resolve()),
                          "actions": len(actions)}, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main()
