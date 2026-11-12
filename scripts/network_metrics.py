"""Core metrics for personal-network analysis (人脉分析).

Pure functions, no I/O beyond loading bundle files, so the scoring rules can be
tested without a live WeChat database.

Data contract: one directory per contact, each containing ``messages.json`` with
the same normalized schema used by she-love-me (sender = me/them, timestamp in
seconds, message_id, type, content).
"""

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SESSION_GAP = 6 * 3600          # 6h of silence starts a new conversation segment
LATENCY_CAP = 2 * 3600          # replies slower than 2h score zero on speed
FREQ_CAP = 30000                # message count that saturates the frequency term
RECENCY_HALFLIFE_DAYS = 120

TIER_CORE = 82
TIER_ACTIVE = 62
DORMANT_DAYS = 90
LOST_DAYS = 365

SERVICE_PREFIXES = ("gh_",)
SERVICE_USERNAMES = {
    "filehelper", "weixin", "notifymessage", "fmessage", "medianote",
    "floatbottle", "qmessage", "qqmail", "weibo", "tmessage", "newsapp",
    "blogapp", "linkedinplugin", "voipnotify",
}
SERVICE_NAMES = {
    "文件传输助手", "微信团队", "服务通知", "朋友推荐消息", "漂流瓶", "语音记事本",
}


# ---------------------------------------------------------------- helpers

def now_seconds():
    return int(datetime.now(timezone.utc).timestamp())


def median(values):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _message_time(message):
    value = message.get("timestamp")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def classify_kind(username, display):
    """Return person / group / official for a conversation."""
    username = username or ""
    if username.endswith("@chatroom"):
        return "group"
    if username.startswith(SERVICE_PREFIXES) or username in SERVICE_USERNAMES:
        return "official"
    if (display or "") in SERVICE_NAMES:
        return "official"
    return "person"


# ---------------------------------------------------------------- per conversation

def conversation_metrics(messages, now=None):
    """Compute behavioural metrics for one conversation.

    ``messages`` need not be normalized; missing timestamps are ignored.
    Returns ``None`` when there is nothing to measure.
    """
    now = now or now_seconds()
    cleaned = []
    for message in messages:
        timestamp = _message_time(message)
        if timestamp is None:
            continue
        cleaned.append({
            "timestamp": timestamp,
            "sender": "me" if message.get("sender") == "me" else "them",
            "type": message.get("type") or "text",
            "content": message.get("content") or "",
        })
    if not cleaned:
        return None
    cleaned.sort(key=lambda item: item["timestamp"])

    mine = [m for m in cleaned if m["sender"] == "me"]
    theirs = [m for m in cleaned if m["sender"] != "me"]
    first, last = cleaned[0]["timestamp"], cleaned[-1]["timestamp"]

    starts = [0]
    for index in range(1, len(cleaned)):
        if cleaned[index]["timestamp"] - cleaned[index - 1]["timestamp"] > SESSION_GAP:
            starts.append(index)
    sessions_mine = sum(1 for index in starts if cleaned[index]["sender"] == "me")
    sessions_theirs = len(starts) - sessions_mine

    latency_me, latency_them = [], []
    for index in range(1, len(cleaned)):
        previous, current = cleaned[index - 1], cleaned[index]
        gap = current["timestamp"] - previous["timestamp"]
        if gap <= 0 or gap > 86400:
            continue
        if current["sender"] == "me" and previous["sender"] == "them":
            latency_me.append(gap)
        elif current["sender"] == "them" and previous["sender"] == "me":
            latency_them.append(gap)

    months = {int(m["timestamp"] // 2592000) for m in cleaned}
    days = {int(m["timestamp"] // 86400) for m in cleaned}
    recent_30 = sum(1 for m in cleaned if m["timestamp"] >= now - 30 * 86400)
    previous_30 = sum(1 for m in cleaned if now - 60 * 86400 <= m["timestamp"] < now - 30 * 86400)

    types = Counter(m["type"] for m in cleaned)
    total = len(cleaned)
    metrics = {
        "total": total,
        "mine": len(mine),
        "theirs": len(theirs),
        "first": int(first),
        "last": int(last),
        "span_days": round((last - first) / 86400, 1),
        "days_since": round(max(0.0, (now - last) / 86400), 1),
        "active_months": len(months),
        "active_days": len(days),
        "sessions": len(starts),
        "sessions_mine": sessions_mine,
        "sessions_theirs": sessions_theirs,
        "reply_me_median": median(latency_me),
        "reply_them_median": median(latency_them),
        "reply_me_n": len(latency_me),
        "reply_them_n": len(latency_them),
        "types": dict(types),
        "last_is_theirs": cleaned[-1]["sender"] != "me",
        "last30": recent_30,
        "prev30": previous_30,
    }
    metrics["dominance"] = round(metrics["mine"] / total, 3)
    metrics["my_daily"] = round(metrics["mine"] / max(len(days), 1), 2)
    metrics["momentum"] = recent_30 - previous_30
    return metrics


def score_strength(metrics):
    """0-100 relationship strength.

    Frequency 28% + recency 30% + reciprocity 18% + continuity 12% + speed 12%.
    """
    total = max(metrics["total"], 1)
    frequency = min(1.0, math.log10(total) / math.log10(FREQ_CAP))
    recency = math.exp(-metrics["days_since"] / RECENCY_HALFLIFE_DAYS)
    balance = 1 - abs(metrics["mine"] - metrics["theirs"]) / max(metrics["mine"] + metrics["theirs"], 1)
    continuity = min(1.0, metrics["active_months"] / 12)
    latency = metrics.get("reply_them_median")
    speed = max(0.0, min(1.0, 1 - latency / LATENCY_CAP)) if latency else 1.0
    return round(100 * (0.28 * frequency + 0.30 * recency + 0.18 * balance
                        + 0.12 * continuity + 0.12 * speed), 1)


def tier_of(metrics):
    if metrics["strength"] >= TIER_CORE:
        return "核心圈"
    if metrics["strength"] >= TIER_ACTIVE:
        return "活跃层"
    if metrics["days_since"] > LOST_DAYS:
        return "失联层"
    if metrics["days_since"] > DORMANT_DAYS:
        return "沉睡层"
    return "外围层"


def tag_of(metrics):
    """Short human label used across reports."""
    if metrics["days_since"] > LOST_DAYS:
        return "已失联"
    if metrics["days_since"] > DORMANT_DAYS:
        return "已冷却"
    if metrics["total"] <= 10:
        return "一次接触"
    if metrics["dominance"] >= 0.65:
        return "你单方面输出"
    init = metrics["sessions_theirs"] / max(metrics["sessions"], 1)
    if init >= 0.7:
        return "对方在主动"
    if metrics.get("group_count", 0) >= 5:
        return "跨群节点"
    if metrics["dominance"] <= 0.4:
        return "对方主导"
    if metrics["strength"] >= TIER_ACTIVE:
        return "稳定双向"
    return "低频维持"


# ---------------------------------------------------------------- bundles

def load_bundles(root):
    """Load every ``<contact>/messages.json`` under *root*.

    Returns a list of {username, display, kind, messages, path}.
    """
    root = Path(root)
    bundles = []
    if not root.exists():
        return bundles
    candidates = []
    if (root / "messages.json").exists():
        candidates.append(root / "messages.json")
    else:
        candidates.extend(sorted(root.glob("*/messages.json")))
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        messages = payload.get("messages") if isinstance(payload, dict) else payload
        if not isinstance(messages, list) or not messages:
            continue
        username = (payload.get("contact_username") if isinstance(payload, dict) else None) or path.parent.name
        display = (payload.get("contact_display") if isinstance(payload, dict) else None) or username
        bundles.append({
            "username": str(username),
            "display": str(display),
            "kind": classify_kind(str(username), str(display)),
            "messages": messages,
            "path": str(path),
        })
    return bundles


# ---------------------------------------------------------------- graph

def build_person_person_edges(membership, usernames):
    """Weighted co-membership edges between people who have a 1:1 conversation."""
    index = {name: i for i, name in enumerate(sorted(usernames))}
    weights = Counter()
    by_group = defaultdict(list)
    for user, groups in membership.items():
        if user not in index:
            continue
        for group in groups:
            by_group[group].append(user)
    for group, members in by_group.items():
        members = sorted(set(members))
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                key = (a, b) if index[a] < index[b] else (b, a)
                weights[key] += 1
    return [
        {"a": a, "b": b, "weight": weight}
        for (a, b), weight in weights.items()
    ]


def adjacency(nodes, edges):
    adj = {node: {} for node in nodes}
    for edge in edges:
        a, b, w = edge["a"], edge["b"], edge.get("weight", 1)
        if a not in adj or b not in adj:
            continue
        adj[a][b] = adj[a].get(b, 0) + w
        adj[b][a] = adj[b].get(a, 0) + w
    return adj


def betweenness(nodes, adj):
    """Brandes' algorithm, unweighted, for moderate graphs (<2k nodes)."""
    cb = {node: 0.0 for node in nodes}
    for source in nodes:
        stack = []
        predecessors = {node: [] for node in nodes}
        sigma = {node: 0.0 for node in nodes}
        sigma[source] = 1.0
        distance = {node: -1 for node in nodes}
        distance[source] = 0
        queue = [source]
        head = 0
        while head < len(queue):
            vertex = queue[head]
            head += 1
            stack.append(vertex)
            for neighbour in adj.get(vertex, {}):
                if distance[neighbour] < 0:
                    distance[neighbour] = distance[vertex] + 1
                    queue.append(neighbour)
                if distance[neighbour] == distance[vertex] + 1:
                    sigma[neighbour] += sigma[vertex]
                    predecessors[neighbour].append(vertex)
        delta = {node: 0.0 for node in nodes}
        while stack:
            vertex = stack.pop()
            for predecessor in predecessors[vertex]:
                if sigma[vertex]:
                    delta[predecessor] += sigma[predecessor] / sigma[vertex] * (1 + delta[vertex])
            if vertex != source:
                cb[vertex] += delta[vertex]
    if len(nodes) > 2:
        scale = 1.0 / ((len(nodes) - 1) * (len(nodes) - 2))
        cb = {node: round(value * scale, 4) for node, value in cb.items()}
    return cb


def label_propagation(nodes, adj, iterations=20):
    """Cheap community detection; deterministic ordering for reproducible output."""
    labels = {node: node for node in nodes}
    ordered = sorted(nodes)
    for _ in range(iterations):
        changed = False
        for node in ordered:
            neighbours = adj.get(node) or {}
            if not neighbours:
                continue
            votes = Counter()
            for neighbour, weight in neighbours.items():
                votes[labels[neighbour]] += weight
            if not votes:
                continue
            best, _ = max(votes.items(), key=lambda item: (item[1], item[0]))
            if labels[node] != best:
                labels[node] = best
                changed = True
        if not changed:
            break
    # normalise so communities are numbered by size
    sizes = Counter(labels.values())
    order = {label: index for index, (label, _) in enumerate(sizes.most_common(), start=1)}
    return {node: order[label] for node, label in labels.items()}


def constraint(nodes, adj):
    """Burt's structural-hole constraint (lower = more brokerage)."""
    result = {}
    for node in nodes:
        neighbours = adj.get(node) or {}
        total = sum(neighbours.values()) or 1
        proportions = {n: w / total for n, w in neighbours.items()}
        value = 0.0
        for j, p_ij in proportions.items():
            indirect = 0.0
            for k, p_ik in proportions.items():
                if k == j:
                    continue
                shared = adj.get(j, {}).get(k, 0)
                denominator = sum(adj.get(j, {}).values()) or 1
                indirect += p_ik * (shared / denominator)
            value += (p_ij + indirect) ** 2
        result[node] = round(value, 4)
    return result


def bridge_score(node, membership, chat_users, group_members=None):
    """How many distinct chat-contacts a person can introduce through groups."""
    reach = set()
    if group_members:
        for group in membership.get(node, []):
            for other in group_members.get(group, []):
                user = other.get("username") if isinstance(other, dict) else other
                if user and user != node and user in chat_users:
                    reach.add(user)
    return len(reach)


# ---------------------------------------------------------------- actions

def weekly_actions(persons, limit=6):
    """Return the small set of actions that actually move relationships."""
    actions = []
    for person in persons:
        if person.get("kind") != "person":
            continue
        name = person.get("name") or person.get("username")
        days = person.get("days_since", 0)
        total = person.get("total", 0)
        if person.get("last_is_theirs") and days >= 3:
            actions.append({
                "type": "关系债",
                "priority": round(person["strength"] * min(days / 30, 1) * 1.2, 2),
                "name": name, "username": person["username"], "days": round(days),
                "reason": f"最后一条是对方发的，已 {round(days)} 天",
                "action": "回一条具体的话，别只回“在”",
            })
        elif total >= 300 and 30 <= days <= 120:
            actions.append({
                "type": "正在冷却",
                "priority": round(total / 50 + days / 30, 2),
                "name": name, "username": person["username"], "days": round(days),
                "reason": f"历史 {total} 条，{round(days)} 天没动",
                "action": "给一个具体的近况或问题，不要群发问候",
            })
        elif total >= 100 and 120 < days <= 730:
            actions.append({
                "type": "沉睡资产",
                "priority": round(total / 60, 2),
                "name": name, "username": person["username"], "days": round(days),
                "reason": f"曾经 {total} 条，已沉睡 {round(days)} 天",
                "action": "用共同经历做切口，一条消息即可",
            })
        elif not person.get("group_count") and 3 <= days <= 30 and total <= 10:
            actions.append({
                "type": "一次接触",
                "priority": round(person["strength"] / 20, 2),
                "name": name, "username": person["username"], "days": round(days),
                "reason": "加了好友但只有几次对话",
                "action": "48 小时内补一个具体信息或请求",
            })
    actions.sort(key=lambda item: -item["priority"])
    return actions[:limit]


def summarize(persons):
    total_messages = sum(p["total"] for p in persons if p.get("kind") != "official")
    people = [p for p in persons if p.get("kind") == "person"]
    return {
        "persons": len(people),
        "groups": len({g for p in persons for g in p.get("shared_groups", [])}),
        "total_messages": total_messages,
        "core": sum(1 for p in people if p["tier"] == "核心圈"),
        "active": sum(1 for p in people if p["tier"] == "活跃层"),
        "dormant": sum(1 for p in people if p["tier"] == "沉睡层"),
        "lost": sum(1 for p in people if p["tier"] == "失联层"),
        "peripheral": sum(1 for p in people if p["tier"] == "外围层"),
        "debt": sum(1 for p in people if p.get("last_is_theirs") and p.get("days_since", 0) >= 3),
        "bridges": sum(1 for p in people if p.get("bridge_score", 0) >= 2),
    }
