"""Detect intimate-relationship candidates from structure and language signals.

This is deliberately conservative: it outputs "候选（待你确认）", never "恋爱".
The signals are structural (late-night share, streaks, media ratio) plus a small
keyword list; every hit carries the message ID so the claim can be checked.

    python scripts/network_intimacy.py --graph data/network/graph.json \
        --output data/network/intimacy.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STRONG = {"想你", "想见你", "喜欢你", "爱你", "在一起", "老公", "老婆", "亲亲", "么么", "抱抱"}
WEAK = {"晚安", "早安", "宝贝", "亲爱的", "宝宝", "约会"}
KEYWORDS = sorted(STRONG | WEAK)
MEDIA_TYPES = {"emoji", "image", "voice", "video"}


def load_bundle(person):
    path = person.get("bundle_path")
    if not path or not Path(path).exists():
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return payload.get("messages", [])


def analyse(person, messages, tz_offset=8, min_messages=100):
    if len(messages) < min_messages:
        return None
    late = 0
    media = 0
    strong_hits = 0
    weak_hits = 0
    hits = []
    days = set()
    for message in messages:
        stamp = message.get("timestamp")
        if isinstance(stamp, (int, float)):
            local = datetime.fromtimestamp(stamp + tz_offset * 3600, timezone.utc)
            if local.hour in (23, 0, 1, 2):
                late += 1
            days.add(local.strftime("%Y-%m-%d"))
        if message.get("type") in MEDIA_TYPES:
            media += 1
        text = (message.get("content") or "")
        if message.get("type") == "text":
            if any(keyword in text for keyword in STRONG):
                strong_hits += 1
                hits.append({"message_id": message.get("message_id"), "quote": text[:40], "kind": "strong"})
            elif any(keyword in text for keyword in WEAK):
                weak_hits += 1
                hits.append({"message_id": message.get("message_id"), "quote": text[:40], "kind": "weak"})
    total = len(messages)
    late_ratio = late / total
    media_ratio = media / total
    keyword_score = min(1.0, (strong_hits * 2 + weak_hits) / 12)

    ordered = sorted(day for day in days)
    max_streak = streak = 0
    previous = None
    for day in ordered:
        current = datetime.strptime(day, "%Y-%m-%d").date()
        if previous and (current - previous).days == 1:
            streak += 1
        else:
            streak = 1
        max_streak = max(max_streak, streak)
        previous = current

    strength = person["strength"] / 100
    balance = 1 - abs(person["mine"] - person["theirs"]) / max(person["mine"] + person["theirs"], 1)
    score = (0.28 * strength
             + 0.20 * min(1.0, late_ratio / 0.25)
             + 0.20 * keyword_score
             + 0.12 * min(1.0, max_streak / 30)
             + 0.10 * balance
             + 0.10 * min(1.0, media_ratio / 0.30))
    # 共同群越多，越可能是同事/同学而不是亲密关系：做一点结构性折扣
    overlap = person.get("group_count", 0)
    score -= min(0.12, max(0, overlap - 4) * 0.012)
    if strong_hits >= 5 and late_ratio >= 0.15 and overlap <= 8:
        confidence = "high"
    elif strong_hits >= 2 or late_ratio >= 0.20:
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "username": person["username"],
        "name": person["name"],
        "score": round(score, 3),
        "confidence": confidence,
        "signals": {
            "late_night_ratio": round(late_ratio, 3),
            "strong_hits": strong_hits,
            "weak_hits": weak_hits,
            "max_streak_days": max_streak,
            "media_ratio": round(media_ratio, 3),
            "balance": round(balance, 3),
            "strength": person["strength"],
        },
        "evidence": hits[-6:],
        "metrics": {
            "total": person["total"],
            "days_since": round(person["days_since"], 1),
            "span_days": person["span_days"],
            "group_count": person.get("group_count", 0),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="检测亲密关系候选（待确认）")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--output", default="data/network/intimacy.json")
    parser.add_argument("--min-messages", type=int, default=100)
    parser.add_argument("--min-score", type=float, default=0.55)
    parser.add_argument("--tz-offset", type=int, default=8)
    parser.add_argument("--overrides", help="JSON: {username: confirmed|excluded}")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    override_path = Path(args.overrides) if args.overrides else Path(args.output).with_name("intimacy_overrides.json")
    overrides = json.loads(override_path.read_text(encoding="utf-8")) if override_path.exists() else {}

    results = []
    excluded = []
    for person in graph["persons"]:
        if person.get("kind") != "person":
            continue
        item = analyse(person, load_bundle(person), args.tz_offset, args.min_messages)
        if not item or item["score"] < args.min_score:
            continue
        status = overrides.get(person["username"])
        if status == "excluded":
            excluded.append({"name": item["name"], "username": item["username"], "score": item["score"]})
            continue
        item["status"] = status or "candidate"
        results.append(item)
    results.sort(key=lambda item: (-item["score"], item["name"]))

    payload = {
        "schema_version": "1.0",
        "messages_digest": graph.get("messages_digest"),
        "generated_at": graph.get("generated_at"),
        "note": "结构性候选，不等于恋爱关系；需要用户确认。工具不判断感情，只提供信号。",
        "candidates": results,
        "excluded": excluded,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "output": str(output.resolve()),
        "candidates": len(results),
        "top": [{"name": c["name"], "score": c["score"]} for c in results[:5]],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
