"""Build a personal-network graph from normalized chat bundles.

Reads:
  data/contacts/<contact>/messages.json     (produced by convert_*.py)
  --names  contacts + group names (optional)
  --rooms  group members and inviters (optional)
  --labels manual labels / resource tier (optional)

Writes:
  data/network/graph.json
  data/network/persons.csv
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import network_metrics as nm  # noqa: E402
from message_normalizer import digest as fingerprint, messages_digest  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_json(path):
    if not path:
        return None
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def parse_names(payload):
    """Accept several shapes and return (contacts_map, rooms_map)."""
    contacts, rooms = {}, {}
    if not payload:
        return contacts, rooms
    if isinstance(payload, dict) and isinstance(payload.get("contacts"), list):
        for item in payload["contacts"]:
            username = item.get("username") or item.get("userName")
            if not username:
                continue
            contacts[username] = {
                "remark": item.get("remark") or "",
                "nickname": item.get("nickname") or item.get("nick_name") or "",
                "alias": item.get("alias") or "",
            }
        raw_rooms = payload.get("rooms")
        if isinstance(raw_rooms, dict):
            rooms.update({k: v for k, v in raw_rooms.items() if isinstance(v, str)})
        elif isinstance(raw_rooms, list):
            for item in raw_rooms:
                username = item.get("username")
                name = item.get("name") or item.get("remark") or item.get("nick_name")
                if username and name:
                    rooms[username] = name
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, str):
                rooms[key] = value
            elif isinstance(value, dict):
                contacts[key] = {
                    "remark": value.get("remark") or "",
                    "nickname": value.get("nickname") or value.get("nick_name") or "",
                    "alias": value.get("alias") or "",
                }
    return contacts, rooms


def parse_rooms(payload):
    """Return {group_username: [{username, display, inviter}]} plus owner/member_count."""
    groups, owners, counts = {}, {}, {}
    if not payload:
        return groups, owners, counts
    raw = payload.get("rooms") if isinstance(payload, dict) and isinstance(payload.get("rooms"), list) else payload
    if isinstance(raw, list):
        for item in raw:
            username = item.get("username")
            if not username:
                continue
            members = []
            for member in item.get("members") or []:
                user = member.get("userName") or member.get("username")
                if not user:
                    continue
                members.append({
                    "username": user,
                    "display": member.get("displayName") or member.get("display") or "",
                    "inviter": member.get("inviter") or "",
                })
            groups[username] = members
            owners[username] = item.get("owner") or ""
            counts[username] = item.get("memberCount") or item.get("member_count") or len(members)
    elif isinstance(raw, dict):
        for username, members in raw.items():
            if isinstance(members, dict):
                members = members.get("members") or []
            if not isinstance(members, list):
                continue
            cleaned = []
            for member in members:
                if isinstance(member, str):
                    cleaned.append({"username": member, "display": "", "inviter": ""})
                elif isinstance(member, dict):
                    user = member.get("userName") or member.get("username")
                    if user:
                        cleaned.append({
                            "username": user,
                            "display": member.get("displayName") or member.get("display") or "",
                            "inviter": member.get("inviter") or "",
                        })
            groups[username] = cleaned
            counts[username] = len(cleaned)
    return groups, owners, counts


def resolve_names(bundles, contacts):
    resolved = {}
    for bundle in bundles:
        username = bundle["username"]
        info = contacts.get(username) or {}
        name = (info.get("remark") or info.get("nickname")
                or (bundle.get("display") if bundle.get("display") != username else "")
                or username)
        resolved[username] = name
    return resolved


def main():
    parser = argparse.ArgumentParser(description="从聊天 bundle 构建人脉图")
    parser.add_argument("--input", default="data/contacts", help="bundle 根目录")
    parser.add_argument("--names", help="联系人/群名称 JSON")
    parser.add_argument("--rooms", help="群成员 JSON（contact-schema --json）")
    parser.add_argument("--labels", help="人工标注 JSON：username -> {tier, role, next}")
    parser.add_argument("--output", default="data/network", help="输出目录")
    parser.add_argument("--me", help="自己的 wxid（默认从 bundle 读取）")
    parser.add_argument("--now", type=int, help="用于复现的当前时间（epoch 秒）")
    parser.add_argument("--since", help="只统计该日期之后（YYYY-MM-DD，UTC）")
    parser.add_argument("--until", help="只统计该日期之前（YYYY-MM-DD，UTC）")
    args = parser.parse_args()

    now = args.now or nm.now_seconds()
    bundles = nm.load_bundles(args.input)
    if not bundles:
        raise SystemExit(f"没有找到 bundle：{args.input}")

    lower = _date_boundary(args.since)
    upper = _date_boundary(args.until)
    if lower or upper:
        for bundle in bundles:
            bundle["messages"] = [
                message for message in bundle["messages"]
                if (lower is None or (nm._message_time(message) or 0) >= lower)
                and (upper is None or (nm._message_time(message) or 0) < upper + 86400)
            ]
        bundles = [bundle for bundle in bundles if bundle["messages"]]

    names_payload = load_json(args.names)
    rooms_payload = load_json(args.rooms)
    labels = load_json(args.labels) or {}
    contacts, room_names = parse_names(names_payload)
    group_members, group_owners, group_counts = parse_rooms(rooms_payload)

    me = args.me
    if not me:
        for bundle in bundles:
            payload = load_json(bundle["path"])
            me = (payload or {}).get("own_wxid")
            if me and me != "unknown":
                break
    me = me or "me"

    names = resolve_names(bundles, contacts)
    for username, info in contacts.items():
        if username not in names and (info.get("remark") or info.get("nickname")):
            names[username] = info.get("remark") or info.get("nickname")

    membership = defaultdict(list)
    for group, members in group_members.items():
        for member in members:
            if member["username"] and member["username"] != me:
                membership[member["username"]].append(group)

    persons, groups = [], []
    digests = {}
    for bundle in bundles:
        metrics = nm.conversation_metrics(bundle["messages"], now=now)
        if not metrics:
            continue
        username = bundle["username"]
        record = {
            "username": username,
            "name": names.get(username) or username,
            "kind": bundle["kind"],
            "bundle_path": bundle["path"],
            **metrics,
        }
        if all(message.get("message_id") for message in bundle["messages"]):
            digests[username] = messages_digest(bundle["messages"])
            record["messages_digest"] = digests[username]
        record["strength"] = nm.score_strength(record)
        record["tier"] = nm.tier_of(record)
        record["tag"] = nm.tag_of(record)
        if bundle["kind"] == "person":
            shared = sorted({room_names.get(g, group_name(g, names)) for g in membership.get(username, [])})
            record["shared_groups"] = shared
            record["group_count"] = len(membership.get(username, []))
            label = labels.get(username) or labels.get(record["name"]) or {}
            if label:
                record["label"] = label
        elif bundle["kind"] == "group":
            members = group_members.get(username, [])
            record["member_count"] = group_counts.get(username) or len(members)
            record["owner"] = group_owners.get(username) or ""
            record["owner_name"] = names.get(record["owner"], record["owner"])
            record["member_usernames"] = [m["username"] for m in members]
            record["i_am_owner"] = record["owner"] == me
        persons.append(record)
        if bundle["kind"] == "group":
            groups.append(record)

    chat_users = {p["username"] for p in persons if p["kind"] == "person"}
    edges = nm.build_person_person_edges(membership, chat_users)
    adj = nm.adjacency(chat_users, edges)
    degree = {node: len(neighbours) for node, neighbours in adj.items()}
    between = nm.betweenness(sorted(chat_users), adj)
    communities = nm.label_propagation(sorted(chat_users), adj)
    constraints = nm.constraint(sorted(chat_users), adj)

    for person in persons:
        if person["kind"] != "person":
            continue
        username = person["username"]
        person["degree"] = degree.get(username, 0)
        person["betweenness"] = between.get(username, 0.0)
        person["community"] = communities.get(username, 0)
        person["constraint"] = constraints.get(username, 1.0)
        person["bridge_score"] = nm.bridge_score(username, membership, chat_users, group_members)
        person["shared_groups"] = person.get("shared_groups", [])

    persons.sort(key=lambda item: -item["strength"])
    groups.sort(key=lambda item: -item["total"])

    stats = nm.summarize(persons)
    stats["shared_groups"] = stats.pop("groups", 0)
    stats["groups"] = len(groups)

    series = Counter()
    for bundle in bundles:
        if bundle["kind"] != "person":
            continue
        for message in bundle["messages"]:
            ts = nm._message_time(message)
            if not ts:
                continue
            stamp = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")
            series[stamp] += 1

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    graph = {
        "schema_version": "1.0",
        "generated_at": now,
        "me": {"username": me, "name": names.get(me, me)},
        "window": {
            "first": min(p["first"] for p in persons),
            "last": max(p["last"] for p in persons),
        },
        "messages_digest": fingerprint({"persons": digests}),
        "stats": stats,
        "persons": persons,
        "groups": groups,
        "edges": edges,
        "series": sorted(series.items()),
        "graph": {
            "degree": degree,
            "betweenness": between,
            "community": communities,
            "constraint": constraints,
        },
    }
    (output / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")

    with open(output / "persons.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["姓名", "username", "类型", "层级", "强度", "消息", "我发", "对方发",
                         "我的占比", "会话段", "最近(天)", "共同群", "桥接分", "中介中心性",
                         "约束指数", "标签", "圈层标注", "身份"])
        for person in persons:
            label = person.get("label") or {}
            writer.writerow([
                person["name"], person["username"], person["kind"], person["tier"],
                person["strength"], person["total"], person["mine"], person["theirs"],
                person["dominance"], person["sessions"], round(person["days_since"]),
                person.get("group_count", 0), person.get("bridge_score", 0),
                person.get("betweenness", 0), person.get("constraint", 0),
                person["tag"], label.get("tier", ""), label.get("role", ""),
            ])

    stats = graph["stats"]
    print(json.dumps({
        "status": "ok",
        "output": str((output / "graph.json").resolve()),
        "persons": stats["persons"],
        "groups": stats["groups"],
        "messages": stats["total_messages"],
        "tiers": {k: stats[k] for k in ("core", "active", "dormant", "lost", "peripheral")},
        "debt": stats["debt"],
        "bridges": stats["bridges"],
    }, ensure_ascii=False, indent=1))


def group_name(username, names):
    return names.get(username) or f"群 {username[:10]}"


def _date_boundary(value):
    if not value:
        return None
    from datetime import datetime, timezone
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


if __name__ == "__main__":
    main()
