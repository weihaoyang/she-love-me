"""Validate that a network analysis is bound to the current data.

Mirrors she-love-me's evidence protocol: every claim that cites messages must
reference real ``msg_`` IDs from the current bundles, and every ``stats_fields``
path must resolve against the current graph.

    python scripts/network_evidence.py --graph data/network/graph.json \
        --analysis data/network/analysis.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MESSAGE_ID = re.compile(r"msg_[0-9a-f]{64}$")


def iter_evidence(value, path="analysis"):
    if isinstance(value, dict):
        if "evidence_message_ids" in value or "stats_fields" in value:
            yield path, value
        for key, child in value.items():
            yield from iter_evidence(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_evidence(child, f"{path}[{index}]")


def resolve_field(graph, field):
    if not isinstance(field, str) or not field:
        raise ValueError("stats_fields 必须是非空路径")
    parts = field.split(".")
    if parts[0] == "stats":
        value = graph["stats"]
        parts = parts[1:]
    elif parts[0] == "window":
        return graph["window"].get(".".join(parts[1:]))
    elif parts[0] == "person":
        if len(parts) < 3:
            raise ValueError(f"person 字段需要 person.<username>.<field>：{field}")
        username, attribute = parts[1], ".".join(parts[2:])
        person = next((p for p in graph["persons"] if p["username"] == username), None)
        if not person:
            raise ValueError(f"person 不存在：{username}")
        value = person
        parts = [attribute]
    elif parts[0] == "graph":
        if len(parts) < 3:
            raise ValueError(f"graph 字段需要 graph.<metric>.<username>：{field}")
        metric, username = parts[1], ".".join(parts[2:])
        if metric not in graph.get("graph", {}):
            raise ValueError(f"图指标不存在：{metric}")
        return graph["graph"][metric].get(username)
    else:
        raise ValueError(f"未知字段前缀：{parts[0]}")
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            raise ValueError(f"统计证据字段不存在：{field}")
        value = value[part]
    return value


def load_message_index(graph, wanted=None):
    """message_id -> (content, transcript) for the cited people only."""
    index = {}
    for person in graph["persons"]:
        if person.get("kind") != "person":
            continue
        if wanted is not None and person["username"] not in wanted:
            continue
        path = person.get("bundle_path")
        if not path or not Path(path).exists():
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        for message in payload.get("messages", []):
            message_id = message.get("message_id")
            if message_id:
                index[message_id] = (message.get("content") or "", message.get("transcript") or "")
    return index


def validate(graph, analysis, strict=True):
    if analysis.get("messages_digest") != graph.get("messages_digest"):
        raise ValueError("分析的数据摘要与当前图谱不一致；请重新运行 network_build.py")

    entries = list(iter_evidence(analysis))
    wanted_ids = set()
    wanted_people = set()
    for _, entry in entries:
        username = entry.get("username")
        if username:
            wanted_people.add(username)
        for message_id in entry.get("evidence_message_ids") or []:
            if not isinstance(message_id, str) or not MESSAGE_ID.fullmatch(message_id):
                raise ValueError(f"{_} 的消息 ID 格式无效：{message_id!r}")
            wanted_ids.add(message_id)
    index = load_message_index(graph, wanted_people or None)
    missing = wanted_ids - set(index)
    if missing:
        raise ValueError(f"引用了不存在的消息：{sorted(missing)[:3]}")

    checked_ids = 0
    warnings = []
    for path, entry in entries:
        level = entry.get("evidence_level")
        if level not in (None, "high", "medium", "low", "insufficient"):
            raise ValueError(f"{path} 的证据等级无效")
        ids = entry.get("evidence_message_ids") or []
        fields = entry.get("stats_fields") or []
        if not isinstance(ids, list) or not isinstance(fields, list):
            raise ValueError(f"{path} 的证据引用必须是数组")
        if strict and level in ("high", "medium") and not ids and not fields:
            raise ValueError(f"{path} 的中高等级证据必须引用消息或统计字段")
        for field in fields:
            value = resolve_field(graph, field)
            if value is None and level in ("high", "medium"):
                raise ValueError(f"{path} 把缺失字段当成有效证据：{field}")
        quote = entry.get("quote")
        if quote:
            hit = any(str(quote) in content or str(quote) in transcript
                      for content, transcript in (index[mid] for mid in ids))
            if not hit:
                raise ValueError(f"{path} 的引用原文与关联消息不符")
        checked_ids += len(ids)
    if not entries:
        warnings.append("分析里没有任何证据引用；结论只能算观察，不能算证明。")
    elif checked_ids == 0:
        warnings.append("分析引用了统计字段，但没有引用任何原始消息；关键结论建议补 1-2 条消息证据。")
    return {"entries": len(entries), "message_ids": checked_ids, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description="校验人脉分析的证据引用")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--analysis", default="data/network/analysis.json")
    parser.add_argument("--no-strict", action="store_true")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    try:
        result = validate(graph, analysis, strict=not args.no_strict)
    except ValueError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
