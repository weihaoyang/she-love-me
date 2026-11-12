"""Bounded evidence retrieval for one person in the network.

Reuses she-love-me's ``query_chat_context.query_context`` so the sampling
budget, digest checks and truncation semantics stay identical.

    python scripts/network_context.py --person "张三" --keyword "合作" --before 5 --after 5
    python scripts/network_context.py --person "张三" --message-id msg_xxx --output scripts/tmp/ctx.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bundle_store import atomic_json  # noqa: E402
from query_chat_context import query_context  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def find_person(graph, needle):
    needle = (needle or "").strip()
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


def main():
    parser = argparse.ArgumentParser(description="按人+关键词/消息 ID 补取证据上下文")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--person", required=True)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--message-id", action="append")
    selector.add_argument("--keyword")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--before", type=int, default=8)
    parser.add_argument("--after", type=int, default=8)
    parser.add_argument("--max-messages", type=int, default=100)
    parser.add_argument("--max-chars", type=int, default=20000)
    parser.add_argument("--expected-digest")
    parser.add_argument("--output")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    person = find_person(graph, args.person)
    if not person:
        raise SystemExit(f"找不到：{args.person}")
    bundle_path = person.get("bundle_path")
    if not bundle_path or not Path(bundle_path).exists():
        raise SystemExit("这个人的 bundle 不存在；重新运行 network_build.py")
    payload = json.loads(Path(bundle_path).read_text(encoding="utf-8-sig"))

    result = query_context(
        payload,
        message_ids=args.message_id,
        keyword=args.keyword,
        since=args.since,
        until=args.until,
        before=args.before,
        after=args.after,
        max_messages=args.max_messages,
        max_chars=args.max_chars,
        expected_digest=args.expected_digest or person.get("messages_digest"),
    )
    result["person"] = {
        "username": person["username"],
        "name": person["name"],
        "strength": person["strength"],
        "tier": person["tier"],
        "days_since": person["days_since"],
    }
    if args.output:
        atomic_json(args.output, result)
        print(json.dumps({"status": "ok", "output": str(Path(args.output).resolve()),
                          "returned": result["returned_count"],
                          "truncated": result["truncated"]}, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
