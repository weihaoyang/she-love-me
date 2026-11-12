"""Ask questions about the network graph.

    python scripts/network_ask.py person 张三
    python scripts/network_ask.py path 张三 李四
    python scripts/network_ask.py debt --limit 10
    python scripts/network_ask.py groups 机器人
    python scripts/network_ask.py who 投资
"""

import argparse
import json
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def index_people(graph):
    people = {}
    for person in graph["persons"]:
        if person.get("kind") != "person":
            continue
        people[person["username"]] = person
    return people


def find_person(graph, needle):
    needle = (needle or "").strip()
    if not needle:
        return None
    for person in graph["persons"]:
        if person.get("kind") != "person":
            continue
        if needle in (person.get("username"), person.get("name")):
            return person
    for person in graph["persons"]:
        if person.get("kind") != "person":
            continue
        if needle in (person.get("name") or ""):
            return person
    return None


def shared_groups(graph, a, b):
    groups = []
    for group in graph.get("groups", []):
        members = set(group.get("member_usernames") or [])
        if a in members and b in members:
            groups.append(group["name"])
    return groups


def build_adjacency(graph):
    adjacency = {}
    for edge in graph.get("edges", []):
        a, b = edge["a"], edge["b"]
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)
    return adjacency


def shortest_path(graph, start, goal, max_hops=6):
    adjacency = build_adjacency(graph)
    queue = deque([(start, [start])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        if node == goal:
            return path
        if len(path) > max_hops:
            continue
        for neighbour in adjacency.get(node, []):
            if neighbour in seen:
                continue
            seen.add(neighbour)
            queue.append((neighbour, path + [neighbour]))
    return None


def describe(person):
    label = person.get("label") or {}
    lines = [
        f"{person['name']}  ({person['username']})",
        f"  层级 {person['tier']} · 状态 {person['tag']} · 强度 {person['strength']}",
        f"  消息 {person['total']}（我 {person['mine']} / 对方 {person['theirs']}），"
        f"会话段 {person['sessions']}（我发起 {person['sessions_mine']}）",
        f"  最近 {person['days_since']:.0f} 天 · 活跃 {person['active_months']} 个月 · 共同群 {person.get('group_count', 0)}",
        f"  桥接分 {person.get('bridge_score', 0)} · 中介中心性 {person.get('betweenness', 0):.3f} · 约束 {person.get('constraint', 0):.3f}",
    ]
    if label:
        lines.append(f"  标注：{label.get('tier', '')} {label.get('role', '')}".rstrip())
        if label.get("next"):
            lines.append(f"  下一步：{label['next']}")
    if person.get("shared_groups"):
        lines.append("  共同群：" + "、".join(person["shared_groups"][:8]))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="查询人脉图")
    parser.add_argument("command", choices=["person", "path", "debt", "groups", "who", "gaps"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    graph = load(args.graph)
    people = index_people(graph)

    if args.command == "person":
        if not args.args:
            raise SystemExit("用法: person <姓名或wxid>")
        person = find_person(graph, args.args[0])
        if not person:
            raise SystemExit(f"找不到：{args.args[0]}")
        if args.json:
            print(json.dumps(person, ensure_ascii=False, indent=1))
        else:
            print(describe(person))

    elif args.command == "path":
        if len(args.args) < 2:
            raise SystemExit("用法: path <A> <B>")
        a = find_person(graph, args.args[0])
        b = find_person(graph, args.args[1])
        if not a or not b:
            raise SystemExit("A 或 B 不在有私聊的人里")
        direct = shared_groups(graph, a["username"], b["username"])
        path = shortest_path(graph, a["username"], b["username"])
        if args.json:
            print(json.dumps({"from": a["name"], "to": b["name"], "direct_groups": direct,
                              "path": [people[u]["name"] for u in path] if path else None},
                             ensure_ascii=False, indent=1))
        else:
            if direct:
                print(f"{a['name']} 和 {b['name']} 直接在同一个群：" + "、".join(direct))
            if path:
                print("路径：" + " → ".join(people[u]["name"] for u in path))
            elif not direct:
                print("在“共同群”图上不连通。")

    elif args.command == "debt":
        rows = [p for p in people.values() if p.get("last_is_theirs") and p.get("days_since", 0) >= 3]
        rows.sort(key=lambda p: -(p["strength"] * min(p["days_since"] / 30, 3)))
        rows = rows[: args.limit]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        else:
            print(f"关系债 {len(rows)} 条（按优先级）")
            for person in rows:
                print(f"  {person['name']:16} {person['days_since']:5.0f} 天  强度 {person['strength']:5.1f}  {person['tag']}")

    elif args.command == "groups":
        keyword = args.args[0] if args.args else ""
        rows = [g for g in graph.get("groups", []) if keyword in g["name"]]
        rows.sort(key=lambda g: -g["total"])
        for group in rows[: args.limit]:
            print(f"{group['name'][:28]:30} {group.get('member_count', 0):4} 人 "
                  f"{group['total']:6} 条  我 {group['mine']:5}  最近 {group['days_since']:.0f} 天")

    elif args.command == "who":
        keyword = args.args[0] if args.args else ""
        rows = []
        for person in people.values():
            label = person.get("label") or {}
            haystack = " ".join([person.get("name") or "", label.get("role") or "",
                                 label.get("tier") or "", " ".join(person.get("shared_groups") or [])])
            if keyword in haystack:
                rows.append(person)
        rows.sort(key=lambda p: -p["strength"])
        for person in rows[: args.limit]:
            label = person.get("label") or {}
            print(f"{person['name'][:18]:20} {label.get('tier', ''):6} {person['strength']:5.1f} "
                  f"{person['total']:6} 条  {person['days_since']:5.0f} 天  {label.get('role', '')}")

    elif args.command == "gaps":
        labels = {}
        for person in people.values():
            tier = (person.get("label") or {}).get("tier")
            if tier:
                entry = labels.setdefault(tier, {"total": 0, "warm": 0, "depth": 0})
                entry["total"] += 1
                entry["depth"] += person["total"]
                if person["days_since"] <= 90:
                    entry["warm"] += 1
        if args.json:
            print(json.dumps(labels, ensure_ascii=False, indent=1))
        else:
            print(f"{'层级':10} {'人数':>4} {'90天内活跃':>8} {'消息总量':>8}")
            for tier, data in sorted(labels.items(), key=lambda item: -item[1]["depth"]):
                print(f"{tier:10} {data['total']:4} {data['warm']:8} {data['depth']:8,}")


if __name__ == "__main__":
    main()
