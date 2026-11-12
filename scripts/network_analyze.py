"""Produce a draft analysis.json for the network, then let an agent enrich it.

The draft is deterministic: every sentence is derived from a metric or a label.
The agent's job is to replace the draft readings with contextual interpretation
and attach real ``msg_`` evidence via ``network_context.py``.

    python scripts/network_analyze.py --graph data/network/graph.json \
        --output data/network/analysis.json --top 12
    python scripts/network_evidence.py --analysis data/network/analysis.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import network_metrics as nm  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def names_of(persons, limit=6):
    return "、".join(p["name"] for p in persons[:limit])


def draft_reading(label, persons, extra=""):
    if not persons:
        return f"{label}目前是空的。"
    total = sum(p["total"] for p in persons)
    warm = sum(1 for p in persons if p["days_since"] <= 90)
    return (f"{label} {len(persons)} 人，共 {total:,} 条消息，其中 {warm} 人最近 90 天有互动。"
            f"代表：{names_of(persons)}。{extra}").strip()


def interpretation(person):
    label = person.get("label") or {}
    role = label.get("role") or "未标注身份"
    return (f"{role}。消息 {person['total']:,} 条（我 {person['mine']} / 对方 {person['theirs']}），"
            f"最近 {person['days_since']:.0f} 天，共同群 {person.get('group_count', 0)} 个，"
            f"状态：{person['tag']}。")


def next_action(person):
    label = person.get("label") or {}
    if label.get("next"):
        return label["next"]
    if person.get("last_is_theirs") and person["days_since"] >= 3:
        return "回一条具体的话，别只回“在”。"
    if person["days_since"] > 120 and person["total"] >= 100:
        return "用共同经历做切口，确认这条线还在。"
    if person["total"] <= 10:
        return "48 小时内补一个具体信息或请求。"
    return "保持当前节奏，下一次给一个具体的结果或问题。"


def build(graph, top=12):
    persons = [p for p in graph["persons"] if p.get("kind") == "person"]
    personas = sorted(persons, key=lambda p: -p["strength"])
    stats = graph["stats"]
    by_tier = {tier: [p for p in personas if p["tier"] == tier]
               for tier in ("核心圈", "活跃层", "沉睡层", "失联层", "外围层")}
    labelled = [p for p in personas if (p.get("label") or {}).get("tier")]
    thin_labelled = [p for p in labelled if p["total"] <= 10]
    debt = [p for p in personas if p.get("last_is_theirs") and p["days_since"] >= 3]
    one_sided = [p for p in personas if p["dominance"] >= 0.65 and p["total"] >= 100]

    total_messages = max(stats["total_messages"], 1)
    top3_share = sum(p["total"] for p in personas[:3]) / total_messages

    thesis = {
        "headline": f"{stats['core']} 个核心、{stats['debt']} 条关系债：网络在维持，不在扩张",
        "summary": (
            f"{stats['persons']} 个有私聊的人里，{stats['core'] + stats['active']} 人有真实热度；"
            f"前三个人的消息量占全部私聊的 {top3_share * 100:.0f}%。"
            f"标注过的 {len(labelled)} 个高价值节点里，{len(thin_labelled)} 个只有个位数消息。"
            f"关系债 {stats['debt']} 条，桥接者 {stats['bridges']} 人。"
        ),
        "evidence_level": "insufficient",
        "evidence_message_ids": [],
        "stats_fields": ["stats.core", "stats.debt", "stats.bridges"],
    }

    layers = []
    for tier in ("核心圈", "活跃层", "沉睡层", "失联层", "外围层"):
        group = by_tier[tier]
        layers.append({
            "name": tier,
            "count": len(group),
            "reading": draft_reading(tier, group),
            "evidence_level": "insufficient",
            "evidence_message_ids": [],
            "stats_fields": [f"stats.{tier_key(tier)}"],
        })

    relations = []
    for person in personas[:top]:
        relations.append({
            "username": person["username"],
            "name": person["name"],
            "role": (person.get("label") or {}).get("role") or "",
            "state": person["tag"],
            "interpretation": interpretation(person),
            "next_action": next_action(person),
            "evidence_level": "insufficient",
            "evidence_message_ids": [],
            "stats_fields": [f"person.{person['username']}.strength",
                             f"person.{person['username']}.total"],
        })

    risks = [
        {
            "type": "集中度",
            "reading": f"前 3 个人占全部私聊消息的 {top3_share * 100:.0f}%；"
                       f"一旦其中一段关系变化，网络会立刻出现空洞。",
            "evidence_level": "low",
            "evidence_message_ids": [],
            "stats_fields": ["stats.total_messages"],
        },
        {
            "type": "关系债",
            "reading": f"{len(debt)} 条会话最后一条是对方发的，且已超过 3 天。",
            "evidence_level": "low",
            "evidence_message_ids": [],
            "stats_fields": ["stats.debt"],
        },
        {
            "type": "单向输出",
            "reading": f"{len(one_sided)} 段关系的发言占比超过 65% 且总量 ≥100 条。",
            "evidence_level": "low",
            "evidence_message_ids": [],
            "stats_fields": ["stats.persons"],
        },
    ]
    if thin_labelled:
        risks.append({
            "type": "名单与关系脱节",
            "reading": f"{len(thin_labelled)} 个高价值标注只有个位数消息："
                       + "、".join(p["name"] for p in thin_labelled[:6]) + "。",
            "evidence_level": "low",
            "evidence_message_ids": [],
            "stats_fields": ["stats.persons"],
        })

    actions = nm.weekly_actions(personas, limit=6)
    for action in actions:
        action["evidence_level"] = "insufficient"
        action["evidence_message_ids"] = []
        action["stats_fields"] = [f"person.{action['username']}.days_since"]

    return {
        "schema_version": "1.0",
        "messages_digest": graph.get("messages_digest"),
        "prompt_version": "network-draft-1.0",
        "model": None,
        "thesis": thesis,
        "layers": layers,
        "relations": relations,
        "risks": risks,
        "actions": actions,
        "draft_note": "这是规则生成的草稿。请用 network_context.py 取证据，改写 reading/interpretation，"
                      "并把真实 msg_ ID 填进 evidence_message_ids；改写后运行 network_evidence.py 校验。",
    }


def tier_key(tier):
    return {"核心圈": "core", "活跃层": "active", "沉睡层": "dormant",
            "失联层": "lost", "外围层": "peripheral"}[tier]


def main():
    parser = argparse.ArgumentParser(description="生成人脉分析草稿 analysis.json")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--output", default="data/network/analysis.json")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    if output.exists() and not args.force:
        raise SystemExit(f"{output} 已存在；追加 --force 才会覆盖（避免冲掉人工分析）。")
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    analysis = build(graph, top=args.top)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(analysis, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "output": str(output.resolve()),
        "relations": len(analysis["relations"]),
        "risks": len(analysis["risks"]),
        "actions": len(analysis["actions"]),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
