"""Generate a single-person profile page (or a set of them).

    python scripts/network_person.py --person "张三"
    python scripts/network_person.py --top 10
"""

import argparse
import html
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import network_metrics as nm  # noqa: E402
from network_report import CSS, esc, fmt_days, fmt_date, sparkline  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


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


def monthly_series(person):
    path = person.get("bundle_path")
    if not path or not Path(path).exists():
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    counter = Counter()
    for message in payload.get("messages", []):
        timestamp = message.get("timestamp")
        if not isinstance(timestamp, (int, float)):
            continue
        counter[datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m")] += 1
    return sorted(counter.items())


def shared_group_rows(graph, person):
    rows = []
    for group in graph.get("groups", []):
        if person["username"] in (group.get("member_usernames") or []):
            share = group["mine"] / group["total"] if group["total"] else 0
            rows.append(f'<tr><td>{esc(group["name"])}</td><td class="num">{group.get("member_count", 0)}</td>'
                        f'<td class="num">{group["total"]:,}</td><td class="num">{share * 100:.1f}%</td>'
                        f'<td class="num">{fmt_days(group["days_since"])}</td></tr>')
    return "".join(rows)


def co_people(graph, person, limit=8):
    groups = {g["username"]: g for g in graph.get("groups", [])}
    mine = {g for g, item in groups.items()
            if person["username"] in (item.get("member_usernames") or [])}
    counter = Counter()
    for group_id in mine:
        for other in groups[group_id].get("member_usernames") or []:
            if other != person["username"]:
                counter[other] += 1
    names = {p["username"]: p["name"] for p in graph["persons"]}
    rows = []
    for username, count in counter.most_common(limit):
        rows.append(f'<tr><td>{esc(names.get(username, username))}</td><td class="num">{count}</td></tr>')
    return "".join(rows)


def relation_block(analysis, person):
    if not analysis:
        return ""
    for relation in analysis.get("relations", []):
        if relation.get("username") == person["username"]:
            evidence = len(relation.get("evidence_message_ids") or [])
            return (f'<div class="node"><div class="h"><span class="nm">分析</span></div>'
                    f'<p>{esc(relation.get("interpretation"))}</p>'
                    f'<p class="sub">证据：{evidence} 条消息（原文默认隐藏）</p>'
                    f'<p class="do">→ {esc(relation.get("next_action"))}</p></div>')
    return ""


def render_person(graph, person, analysis=None):
    label = person.get("label") or {}
    series = monthly_series(person)
    role = label.get("role") or "未标注身份"
    tier = label.get("tier") or person["tier"]
    spark = sparkline(series) if series else '<p class="sub">没有可绘制的消息。</p>'
    co_rows = co_people(graph, person)
    group_rows = shared_group_rows(graph, person)

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(person['name'])} · 人脉档案</title><style>{CSS}</style></head><body><div class="wrap">
<header>
<div class="kicker">PERSON PROFILE</div>
<h1>{esc(person['name'])}</h1>
<p class="sub">{esc(role)} · {esc(tier)} · {esc(person['tag'])}</p>
<div class="cards">
<div class="card"><b>{person['total']:,}</b><span>消息</span></div>
<div class="card"><b>{person['mine']:,}/{person['theirs']:,}</b><span>我 / 对方</span></div>
<div class="card"><b>{person['sessions']}</b><span>会话段</span></div>
<div class="card"><b>{fmt_days(person['days_since'])}</b><span>最近联系</span></div>
<div class="card"><b>{person.get('group_count', 0)}</b><span>共同群</span></div>
<div class="card"><b>{person['strength']:.0f}</b><span>关系强度</span></div>
</div>
</header>
{relation_block(analysis, person)}
<h2>时间线</h2>
{spark}
<h2>共同群</h2>
<table><thead><tr><th>群</th><th class="num">成员</th><th class="num">消息</th><th class="num">我的占比</th><th class="num">最近</th></tr></thead>
<tbody>{group_rows or '<tr><td colspan="5" class="sub">没有共同群</td></tr>'}</tbody></table>
<h2>通过群能连到的人</h2>
<table><thead><tr><th>人</th><th class="num">重叠群数</th></tr></thead>
<tbody>{co_rows or '<tr><td colspan="2" class="sub">没有</td></tr>'}</tbody></table>
<footer>
关系强度 = 频率 28% + 近因 30% + 双向均衡 18% + 持续度 12% + 回复速度 12%。<br>
本页只在本机生成，不含聊天原文与第三方敏感信息。
</footer>
</div></body></html>"""


def safe_name(value):
    text = "".join(ch for ch in value if ch not in '\\/:*?"<>|').strip()
    return text[:40] or "person"


def main():
    parser = argparse.ArgumentParser(description="生成单人档案页")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--analysis")
    parser.add_argument("--person")
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--output", default="reports/network/people")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8")) if args.analysis else None
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    if args.person:
        person = find_person(graph, args.person)
        if not person:
            raise SystemExit(f"找不到：{args.person}")
        targets = [person]
    elif args.top:
        targets = [p for p in graph["persons"] if p.get("kind") == "person"][: args.top]
    else:
        raise SystemExit("需要 --person 或 --top")

    written = []
    links = []
    for person in targets:
        page = output / f"{safe_name(person['name'])}.html"
        page.write_text(render_person(graph, person, analysis), encoding="utf-8")
        written.append(str(page.resolve()))
        links.append(f'<li><a href="{esc(page.name)}">{esc(person["name"])}</a>'
                     f'<span class="sub"> · {person["total"]:,} 条 · {fmt_days(person["days_since"])}</span></li>')

    if len(targets) > 1:
        index = output / "index.html"
        index.write_text(
            f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>人物档案</title><style>{CSS}</style></head><body><div class="wrap">
<header><div class="kicker">PEOPLE INDEX</div><h1>人物档案</h1>
<p class="sub">按关系强度排序的前 {len(targets)} 人。</p></header>
<ul style="font-size:15px;line-height:2.1">{"".join(links)}</ul>
</div></body></html>""", encoding="utf-8")
        written.append(str(index.resolve()))

    print(json.dumps({"status": "ok", "pages": len(written), "files": written[:5]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
