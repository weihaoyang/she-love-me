"""Render a self-contained HTML dashboard from graph.json.

    python scripts/network_report.py --graph data/network/graph.json \
        --output reports/network/dashboard.html
"""

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import network_metrics as nm  # noqa: E402
import network_viz  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def esc(value):
    return html.escape(str(value if value is not None else ""))


def fmt_days(days):
    days = float(days or 0)
    if days < 1:
        return "今天"
    if days < 30:
        return f"{days:.0f} 天前"
    if days < 365:
        return f"{days / 30:.1f} 个月前"
    return f"{days / 365:.1f} 年前"


def fmt_lat(seconds):
    if not seconds:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f} 秒"
    if seconds < 3600:
        return f"{seconds / 60:.0f} 分"
    return f"{seconds / 3600:.1f} 时"


def fmt_date(ts):
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def bar(value, maximum, width=120, color="#3f6f6a"):
    size = max(2, int(value / maximum * width)) if maximum else 2
    return f'<span class="bar"><i style="width:{size}px;background:{color}"></i></span>'


def sparkline(series, width=980, height=150):
    if not series:
        return ""
    values = [value for _, value in series]
    maximum = max(values) or 1
    count = len(series)
    pad_l, pad_b = 40, 22
    step = (width - pad_l - 24) / max(count - 1, 1)
    points = []
    for index, (label, value) in enumerate(series):
        x = pad_l + index * step
        y = height - pad_b - (value / maximum) * (height - pad_b - 12)
        points.append((x, y, value, label))
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y, _, _) in enumerate(points))
    area = (f"M{points[0][0]:.1f},{height - pad_b} "
            + " ".join(f"L{x:.1f},{y:.1f}" for x, y, _, _ in points)
            + f" L{points[-1][0]:.1f},{height - pad_b} Z")
    labels = [i for i in range(count) if i % max(1, count // 8) == 0]
    if count - 1 not in labels:
        labels.append(count - 1)
    ticks = "".join(
        f'<text x="{points[i][0]:.1f}" y="{height - 6}" class="ax" '
        f'text-anchor="{"end" if i == count - 1 else "middle"}">{points[i][3][2:]}</text>'
        for i in labels
    )
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#3f6f6a"/>' for x, y, _, _ in points)
    grid = "".join(
        f'<line x1="{pad_l}" y1="{height - pad_b - f * (height - pad_b - 12):.1f}" '
        f'x2="{width}" y2="{height - pad_b - f * (height - pad_b - 12):.1f}" stroke="#e8e4dd"/>'
        f'<text x="4" y="{height - pad_b - f * (height - pad_b - 12) + 4:.1f}" class="ax">'
        f'{int(maximum * f):,}</text>'
        for f in (1, .5)
    )
    return (f'<svg viewBox="0 0 {width} {height}" class="chart">{grid}'
            f'<path d="{area}" fill="#3f6f6a" opacity=".10"/>'
            f'<path d="{path}" fill="none" stroke="#3f6f6a" stroke-width="1.6"/>{dots}{ticks}</svg>')


def person_rows(persons, show_label=True):
    rows = []
    for index, person in enumerate(persons, 1):
        label = person.get("label") or {}
        badge = f'<span class="badge">{esc(label.get("tier"))}</span>' if label.get("tier") else ""
        role = f'<div class="role">{esc(label.get("role"))}</div>' if label.get("role") else ""
        rows.append(
            "<tr>"
            f'<td class="num">{index}</td>'
            f'<td class="nm">{esc(person["name"])}{badge}{role}</td>'
            f'<td><span class="pill t{index % 5}">{esc(person["tag"])}</span></td>'
            f'<td class="num">{person["total"]:,}</td>'
            f'<td class="num">{person["mine"]:,}/{person["theirs"]:,}</td>'
            f'<td class="num">{person["dominance"]:.2f}</td>'
            f'<td class="num">{person["sessions"]}</td>'
            f'<td class="num">{fmt_days(person["days_since"])}</td>'
            f'<td class="num">{person.get("group_count", 0)}</td>'
            f'<td class="num">{person.get("bridge_score", 0)}</td>'
            f'<td class="num">{person["strength"]:.0f}</td>'
            "</tr>"
        )
    return "".join(rows)


def group_rows(groups, limit=15):
    rows = []
    for group in groups[:limit]:
        share = group["mine"] / group["total"] if group["total"] else 0
        owner = '<span class="badge">我建的</span>' if group.get("i_am_owner") else ""
        rows.append(
            "<tr>"
            f'<td class="nm">{esc(group["name"])}{owner}</td>'
            f'<td class="num">{group.get("member_count", 0)}</td>'
            f'<td class="num">{group["total"]:,}</td>'
            f'<td class="num">{group["mine"]:,}</td>'
            f'<td class="num">{share * 100:.1f}%</td>'
            f'<td class="num">{fmt_days(group["days_since"])}</td>'
            "</tr>"
        )
    return "".join(rows)


def debt_rows(persons):
    debt = [p for p in persons if p.get("last_is_theirs") and p.get("days_since", 0) >= 3]
    debt.sort(key=lambda p: -(p["strength"] * min(p["days_since"] / 30, 3)))
    rows = []
    for person in debt[:18]:
        rows.append(
            "<tr>"
            f'<td class="nm">{esc(person["name"])}</td>'
            f'<td><span class="pill">{esc(person["tag"])}</span></td>'
            f'<td class="num">{person["total"]:,}</td>'
            f'<td class="num">{fmt_days(person["days_since"])}</td>'
            f'<td class="num">{person["strength"]:.0f}</td>'
            "</tr>"
        )
    return "".join(rows), len(debt)


def dormant_rows(persons, limit=10):
    dormant = [p for p in persons if p.get("kind") == "person"
               and p["total"] >= 100 and nm.DORMANT_DAYS <= p["days_since"] <= 730]
    dormant.sort(key=lambda p: -p["total"])
    rows = []
    for person in dormant[:limit]:
        rows.append(
            "<tr>"
            f'<td class="nm">{esc(person["name"])}</td>'
            f'<td class="num">{person["total"]:,}</td>'
            f'<td class="num">{person["active_months"]}</td>'
            f'<td class="num">{fmt_days(person["days_since"])}</td>'
            f'<td class="num">{person["strength"]:.0f}</td>'
            "</tr>"
        )
    return "".join(rows), len(dormant)


def bridge_rows(persons, limit=14):
    bridges = [p for p in persons if p.get("kind") == "person" and (p.get("bridge_score") or 0) >= 2]
    bridges.sort(key=lambda p: (-(p.get("bridge_score") or 0), -(p.get("betweenness") or 0)))
    rows = []
    for person in bridges[:limit]:
        rows.append(
            "<tr>"
            f'<td class="nm">{esc(person["name"])}</td>'
            f'<td class="num">{person.get("group_count", 0)}</td>'
            f'<td class="num">{person.get("bridge_score", 0)}</td>'
            f'<td class="num">{person.get("betweenness", 0):.3f}</td>'
            f'<td class="num">{person["total"]:,}</td>'
            "</tr>"
        )
    return "".join(rows)


def gap_rows(persons):
    labelled = [p for p in persons if p.get("kind") == "person" and (p.get("label") or {}).get("tier")]
    if not labelled:
        return None
    buckets = {}
    for person in labelled:
        tier = person["label"]["tier"]
        bucket = buckets.setdefault(tier, {"total": 0, "warm": 0, "depth": 0})
        bucket["total"] += 1
        bucket["depth"] += person["total"]
        if person["days_since"] <= 90:
            bucket["warm"] += 1
    order = sorted(buckets.items(), key=lambda item: -item[1]["depth"])
    rows = "".join(
        f'<tr><td class="nm">{esc(tier)}</td><td class="num">{data["total"]}</td>'
        f'<td class="num">{data["warm"]}</td><td class="num">{data["depth"]:,}</td>'
        f'<td>{"充足" if data["warm"] >= 3 else ("偏少" if data["warm"] >= 1 else "空白")}</td></tr>'
        for tier, data in order
    )
    return rows


def weekly_rows(actions):
    rows = []
    for index, action in enumerate(actions, 1):
        rows.append(
            "<tr>"
            f'<td class="num">{index}</td>'
            f'<td><span class="pill">{esc(action["type"])}</span></td>'
            f'<td class="nm">{esc(action["name"])}</td>'
            f'<td class="num">{action["days"]} 天</td>'
            f'<td>{esc(action["reason"])}</td>'
            f'<td class="do">{esc(action["action"])}</td>'
            "</tr>"
        )
    return "".join(rows)


def load_quotes(graph, analysis):
    """message_id -> short quote, only for evidence referenced by the analysis."""
    wanted = {}
    for relation in analysis.get("relations", []):
        for message_id in relation.get("evidence_message_ids") or []:
            wanted.setdefault(relation.get("username"), set()).add(message_id)
    quotes = {}
    if not wanted:
        return quotes
    for person in graph["persons"]:
        if person["username"] not in wanted:
            continue
        path = person.get("bundle_path")
        if not path or not Path(path).exists():
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        for message in payload.get("messages", []):
            if message.get("message_id") in wanted[person["username"]]:
                text = (message.get("content") or message.get("transcript") or "").strip()
                if text:
                    quotes[message["message_id"]] = text[:160]
    return quotes


def _deep_summary(name):
    safe = "".join(ch for ch in name if ch not in '\\/:*?"<>|').strip()[:40] or "person"
    path = Path(__file__).resolve().parents[1] / "reports/network/deep" / safe / "deepdive.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def render_intimacy(intimacy):
    if not intimacy or not intimacy.get("candidates"):
        return ""
    blocks = ['<h2>亲密关系<em>候选 · 待你确认</em></h2>',
              f'<p class="sub">{esc(intimacy.get("note"))}</p>']
    for candidate in intimacy["candidates"][:8]:
        signals = candidate.get("signals") or {}
        confidence = candidate.get("confidence", "low")
        deep = _deep_summary(candidate["name"])
        deep_line = ""
        if deep and deep.get("summary"):
            summary = deep["summary"]
            deep_line = (f'<p class="ev">深潜：对称性 {summary.get("symmetry_score")} · '
                         f'我回 {summary.get("my_avg_seconds")} 秒 / 对方回 {summary.get("their_avg_seconds")} 秒'
                         + (' · <a href="deep/%s/report.html">报告</a>' % esc(deep["person"]["name"])
                            if deep.get("report") else "")
                         + '</p>')
        blocks.append(
            f'<div class="rel"><div class="rh"><span class="rn">{esc(candidate["name"])}</span>'
            f'<span class="rtag">{esc(confidence)}</span>'
            f'<span class="rr">score {candidate["score"]:.2f}</span></div>'
            f'<p>深夜占比 {signals.get("late_night_ratio", 0) * 100:.0f}% · '
            f'强信号 {signals.get("strong_hits", 0)} 次 · 弱信号 {signals.get("weak_hits", 0)} 次 · '
            f'最长连续 {signals.get("max_streak_days", 0)} 天 · '
            f'媒体占比 {signals.get("media_ratio", 0) * 100:.0f}% · '
            f'共同群 {candidate.get("metrics", {}).get("group_count", 0)}</p>'
            f'{deep_line}'
            f'<p class="ev">证据：{len(candidate.get("evidence") or [])} 条消息（原文默认隐藏）</p></div>')
    blocks.append('<p class="sub">这是结构信号，不是结论。用 '
                  '<code>data/network/intimacy_overrides.json</code> 标记 '
                  '<code>confirmed</code> / <code>excluded</code> 后重新运行。</p>')
    return "".join(blocks)


def render_analysis(analysis, quotes, show_quotes=False):
    if not analysis:
        return ""
    thesis = analysis.get("thesis") or {}
    blocks = ['<section class="narrative">',
              '<div class="kicker">ANALYSIS · 证据版</div>',
              f'<h2>结论<em>agent narrative</em></h2>',
              f'<p class="thesis">{esc(thesis.get("headline"))}</p>',
              f'<p class="lead">{esc(thesis.get("summary"))}</p>']

    layers = analysis.get("layers") or []
    if layers:
        blocks.append('<h3>分层读数</h3><div class="layers">')
        for layer in layers:
            blocks.append(
                f'<div class="layer"><b>{esc(layer.get("name"))}</b>'
                f'<span class="lv">{layer.get("count", 0)} 人</span>'
                f'<p>{esc(layer.get("reading"))}</p></div>')
        blocks.append('</div>')

    relations = analysis.get("relations") or []
    if relations:
        blocks.append('<h3>关键关系</h3>')
        for relation in relations:
            quote = ""
            for message_id in relation.get("evidence_message_ids") or []:
                if message_id in quotes:
                    quote = quotes[message_id]
                    break
            quote_html = ""
            if quote and show_quotes:
                quote_html = f'<blockquote class="q">“{esc(quote)}”</blockquote>'
            elif relation.get("evidence_message_ids"):
                quote_html = (f'<p class="ev">证据：{len(relation["evidence_message_ids"])} 条消息'
                              f'（原文默认隐藏）</p>')
            blocks.append(
                f'<div class="rel"><div class="rh"><span class="rn">{esc(relation.get("name"))}</span>'
                f'<span class="rr">{esc(relation.get("role"))}</span>'
                f'<span class="rtag">{esc(relation.get("state"))}</span></div>'
                f'<p>{esc(relation.get("interpretation"))}</p>{quote_html}'
                f'<p class="do">→ {esc(relation.get("next_action"))}</p></div>')

    risks = analysis.get("risks") or []
    if risks:
        blocks.append('<h3>风险</h3><ul class="risks">')
        for risk in risks:
            blocks.append(f'<li><b>{esc(risk.get("type"))}</b>：{esc(risk.get("reading"))}</li>')
        blocks.append('</ul>')

    actions = analysis.get("actions") or []
    if actions:
        blocks.append('<h3>本周行动</h3><ol class="acts">')
        for action in actions:
            blocks.append(
                f'<li><b>{esc(action.get("name"))}</b>（{esc(action.get("type"))}，'
                f'{action.get("days", 0)} 天）<br>{esc(action.get("action"))}</li>')
        blocks.append('</ol>')

    blocks.append('</section>')
    return "".join(blocks)


CSS = """
:root{--ink:#22201d;--muted:#7b736a;--line:#e6e1d8;--bg:#faf8f4;--card:#fff;--a:#3f6f6a;--b:#a8703f;--r:#a44b3f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;line-height:1.7;font-size:14.5px}
.wrap{max-width:1180px;margin:0 auto;padding:0 26px 90px}
header{padding:66px 0 34px;border-bottom:1px solid var(--line);margin-bottom:36px}
.kicker{letter-spacing:.26em;font-size:11px;color:var(--muted)}
h1{font-family:"Songti SC","SimSun",serif;font-size:42px;line-height:1.2;margin:14px 0 12px;font-weight:600}
h2{font-family:"Songti SC",serif;font-size:24px;margin:58px 0 6px;font-weight:600}
h2 em{font-style:normal;font-size:12px;color:var(--muted);letter-spacing:.1em;margin-left:10px;font-family:inherit}
h3{font-size:15.5px;margin:26px 0 8px;font-weight:600;color:#4a453f}
p{max-width:920px;color:#4a453f}
.sub{color:var(--muted)}
.lead{font-size:15.5px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px;margin:26px 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:3px;padding:15px 16px}
.card b{display:block;font-size:26px;line-height:1.15;font-weight:600}
.card span{font-size:11.5px;color:var(--muted);letter-spacing:.04em}
table{width:100%;border-collapse:collapse;background:var(--card);margin:12px 0;font-size:13.2px}
th{text-align:left;font-size:11px;letter-spacing:.07em;color:var(--muted);padding:8px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:7px 9px;border-bottom:1px solid #f2eee7;vertical-align:top}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;color:#6b645b}
td.nm{font-weight:500}
td.do{color:var(--a);font-size:12.5px}
.role{font-size:11px;color:var(--muted);font-weight:400}
.badge{display:inline-block;font-size:10px;color:var(--b);border:1px solid #ddc9ae;border-radius:2px;padding:0 4px;margin-left:6px;vertical-align:1px}
.pill{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;background:#f0ece4;color:#5f5850;white-space:nowrap}
.t0{background:#eef3f1;color:#38605c}.t1{background:#f6efe6;color:#8a6034}
.t2{background:#f0eef5;color:#5c5476}.t3{background:#f5eeee;color:#8b4a45}.t4{background:#eef1f6;color:#456079}
.chart{width:100%;height:auto;margin:8px 0 2px}
.ax{font-size:10px;fill:#a49a8e}
.bar{display:inline-block;width:120px;height:8px;background:#efeae1;border-radius:2px;overflow:hidden;vertical-align:middle}
.bar i{display:block;height:100%}
.hbar{display:flex;align-items:center;gap:10px;margin:6px 0;font-size:13px}
.hl{width:180px;color:#4a453f;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hb{flex:1;max-width:340px;height:9px;background:#efeae1;border-radius:2px;overflow:hidden}
.hb i{display:block;height:100%;border-radius:2px}
.hv{color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:30px}
blockquote{margin:18px 0;padding:14px 18px;border-left:2px solid var(--a);background:#f2f0e9;max-width:920px;font-size:14.5px}
footer{margin-top:70px;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
.tools{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;font-size:12px;color:var(--muted)}
.tools code{background:#f1ede6;padding:2px 6px;border-radius:2px}
.narrative{margin-top:10px}
.thesis{font-family:"Songti SC",serif;font-size:22px;line-height:1.4;margin:8px 0 6px;font-weight:600}
.layers{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:10px 0}
.layer{background:var(--card);border:1px solid var(--line);padding:12px 14px;border-radius:3px}
.layer b{font-size:14px}
.layer .lv{float:right;font-size:11px;color:var(--muted)}
.layer p{font-size:12.5px;color:#5c554c;margin:6px 0 0}
.rel{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--a);padding:12px 14px;margin:8px 0;border-radius:2px}
.rel .rh{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.rel .rn{font-weight:600;font-size:15px}
.rel .rr{font-size:12px;color:#5c554c}
.rel .rtag{font-size:10.5px;color:var(--muted);border:1px solid var(--line);padding:0 5px;border-radius:2px}
.rel p{margin:6px 0;font-size:13px}
blockquote.q{margin:8px 0;padding:8px 12px;border-left:2px solid #c9b28e;background:#f7f3ea;font-size:12.5px;color:#5c554c}
.ev{font-size:11.5px;color:var(--muted);margin:6px 0}
.demo{margin:0 0 18px;padding:9px 12px;border:1px solid #e0c9b0;background:#fbf3e9;
color:#8a6034;font-size:12.5px;border-radius:3px}
.demo code{background:#f4e8d8;padding:1px 5px;border-radius:2px}
.netmap{width:100%;height:auto;background:#fbfaf6;border:1px solid var(--line);border-radius:3px;margin:10px 0}
.glabel{font-size:9.5px;fill:#4a453f}
.glegend{font-size:9.5px;fill:#7b736a}
.risks{margin:8px 0 8px 18px;padding:0;font-size:13.5px}
.risks li{margin:5px 0}
.acts{margin:8px 0 8px 20px;padding:0;font-size:13.5px}
.acts li{margin:7px 0}
@media(max-width:860px){.grid2{grid-template-columns:1fr}h1{font-size:32px}.wrap{padding:0 16px 60px}}
"""


def render(graph, title="人脉地图", analysis=None, intimacy=None, show_quotes=False, demo=False):
    persons = [p for p in graph["persons"] if p.get("kind") == "person"]
    groups = graph.get("groups", [])
    stats = graph["stats"]
    me = graph.get("me", {})
    window = graph.get("window", {})
    quotes = load_quotes(graph, analysis) if analysis else {}
    analysis_html = render_analysis(analysis, quotes, show_quotes=show_quotes)
    intimacy_html = render_intimacy(intimacy)
    network_svg = network_viz.render_svg(graph)
    demo_banner = ('<div class="demo">示例数据 · 全部为虚构人物，由 '
                   '<code>network_demo.py</code> 生成，不代表任何真实用户。</div>'
                   if demo else "")
    debt_html, debt_total = debt_rows(persons)
    dormant_html, dormant_total = dormant_rows(persons)
    bridges_html = bridge_rows(persons)
    gaps_html = gap_rows(persons)
    actions = nm.weekly_actions(persons, limit=6)
    core = [p for p in persons if p["tier"] == "核心圈"]
    active = [p for p in persons if p["tier"] == "活跃层"]
    total_messages = stats["total_messages"]
    my_messages = sum(p["mine"] for p in persons)
    group_total = sum(g["total"] for g in groups)
    group_mine = sum(g["mine"] for g in groups)
    group_share = group_mine / max(group_total, 1) * 100
    biggest_dormant = max(
        (p for p in persons if nm.DORMANT_DAYS <= p["days_since"] <= 730 and p["total"] >= 100),
        key=lambda p: p["total"], default=None)
    longest_debt = max(
        (p for p in persons if p.get("last_is_theirs") and 3 <= p["days_since"] <= 365),
        key=lambda p: p["days_since"], default=None)
    warm = stats["core"] + stats["active"]
    warm_share = warm / max(stats["persons"], 1) * 100

    narrative = []
    narrative.append(
        f'{stats["persons"]} 个有私聊的人里，<b>{warm} 个</b>还有真实热度（核心 + 活跃），占 {warm_share:.0f}%；'
        f'剩下 {stats["persons"] - warm} 个处于冷却、失联或“一次接触”。')
    if biggest_dormant:
        narrative.append(
            f'最大的沉睡资产是 <b>{esc(biggest_dormant["name"])}</b>：{biggest_dormant["total"]:,} 条、'
            f'{biggest_dormant["active_months"]} 个月、{fmt_days(biggest_dormant["days_since"])}没动。')
    narrative.append(
        f'关系债 <b>{debt_total} 条</b>' + (f'，最久的是 {esc(longest_debt["name"])}（{round(longest_debt["days_since"])} 天）' if longest_debt else '') + '。')
    narrative.append(
        f'你在 {len(groups)} 个群里只贡献了 {group_share:.1f}% 的发言——群是资源池，不是关系。')

    labelled = [p for p in persons if (p.get("label") or {}).get("tier")]
    label_line = ""
    if labelled:
        thin = sum(1 for p in labelled if p["total"] <= 10)
        label_line = (f'你手动标注了 {len(labelled)} 个高价值节点，其中 <b>{thin} 个只有个位数消息</b>——'
                      f'名单很长，关系很浅。')

    context = {
        "title": title,
        "generated": datetime.fromtimestamp(graph["generated_at"], timezone.utc).strftime("%Y-%m-%d"),
        "window": f'{fmt_date(window.get("first"))} ~ {fmt_date(window.get("last"))}',
        "me": esc(me.get("name") or me.get("username") or "我"),
        "cards": f"""
<div class="cards">
<div class="card"><b>{stats['persons']}</b><span>有私聊的人</span></div>
<div class="card"><b>{total_messages:,}</b><span>私聊消息</span></div>
<div class="card"><b>{len(groups)}</b><span>产生消息的群</span></div>
<div class="card"><b>{stats['core']}</b><span>核心圈</span></div>
<div class="card"><b>{debt_total}</b><span>关系债</span></div>
<div class="card"><b>{stats['bridges']}</b><span>跨群桥接者</span></div>
</div>""",
        "narrative": "".join(f"<p>{line}</p>" for line in narrative) + (f"<p>{label_line}</p>" if label_line else ""),
        "spark": sparkline(graph.get("series", [])),
        "network_svg": network_svg,
        "intimacy_html": intimacy_html,
        "core_rows": person_rows(core),
        "active_rows": person_rows(active, show_label=False),
        "debt_rows": debt_html,
        "dormant_rows": dormant_html,
        "bridge_rows": bridges_html,
        "group_rows": group_rows(groups),
        "gap_table": (
            f"""<table><thead><tr><th>层</th><th class="num">人数</th><th class="num">90 天内活跃</th>
<th class="num">消息总量</th><th>判断</th></tr></thead><tbody>{gaps_html}</tbody></table>"""
            if gaps_html else
            '<p class="sub">没有提供 labels.json。加上 <code>--labels</code> 后，这里会按“资本 / 机构 / 产业 / 学术”统计覆盖度。</p>'
        ),
        "weekly_rows": weekly_rows(actions),
        "roster_rows": person_rows(persons),
        "analysis_html": analysis_html,
        "demo_banner": demo_banner,
    }

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{context['title']} · {context['me']}</title>
<style>{CSS}</style></head><body><div class="wrap">

<header>
{context['demo_banner']}
<div class="kicker">PERSONAL NETWORK DASHBOARD · {context['generated']}</div>
<h1>{context['title']}</h1>
<p class="sub">基于本机聊天记录的关系网络分析。数据窗口 {context['window']}，
共 {stats['persons']} 个有私聊的人、{len(groups)} 个群、{total_messages:,} 条私聊消息。</p>
{context['cards']}
</header>

{context['analysis_html']}
<h2>结构诊断<em>指标</em></h2>
{context['narrative']}

<h2>两年的时间线<em>私聊消息 / 月</em></h2>
{context['spark']}

<h2>关系图<em>共同群 · 前 60 人 + 已标注</em></h2>
<p class="sub">节点大小 = 消息量；颜色 = 最近联系（绿 30 天内 / 橙 30–120 天 / 灰 120 天以上）；
连线 = 共同群，越粗表示重叠的群越多。孤立点代表只私聊、没有群重叠的人。</p>
{context['network_svg']}

{context['intimacy_html']}

<h2>核心圈<em>{len(core)} 人</em></h2>
<table><thead><tr><th class="num">#</th><th>姓名</th><th>状态</th><th class="num">消息</th>
<th class="num">我/对方</th><th class="num">我的占比</th><th class="num">会话段</th><th class="num">最近</th>
<th class="num">共同群</th><th class="num">桥接</th><th class="num">强度</th></tr></thead>
<tbody>{context['core_rows']}</tbody></table>

<h2>活跃层<em>{len(active)} 人</em></h2>
<table><thead><tr><th class="num">#</th><th>姓名</th><th>状态</th><th class="num">消息</th>
<th class="num">我/对方</th><th class="num">我的占比</th><th class="num">会话段</th><th class="num">最近</th>
<th class="num">共同群</th><th class="num">桥接</th><th class="num">强度</th></tr></thead>
<tbody>{context['active_rows']}</tbody></table>

<h2>关系债<em>{debt_total} 条</em></h2>
<p>最后一条消息是对方发的，且已经过去 3 天以上。按「强度 × 沉默时长」排序——强度越高，越不该沉默。</p>
<table><thead><tr><th>姓名</th><th>状态</th><th class="num">历史消息</th><th class="num">已沉默</th>
<th class="num">强度</th></tr></thead><tbody>{context['debt_rows']}</tbody></table>

<h2>沉睡资产<em>{dormant_total} 人</em></h2>
<p>曾经有真实往来（≥100 条），但已经 90 天以上没动。这类关系的复活成本最低。</p>
<table><thead><tr><th>姓名</th><th class="num">历史消息</th><th class="num">活跃月数</th>
<th class="num">已沉默</th><th class="num">强度</th></tr></thead><tbody>{context['dormant_rows']}</tbody></table>

<h2>桥接者<em>跨群 ≥ 2</em></h2>
<p>同时出现在你多个圈子里的人。桥接分 = 他能在群里直接连接到的、你也聊过的人数量；
中介中心性 = 他在你的关系图里有多像“路由器”。</p>
<table><thead><tr><th>姓名</th><th class="num">共同群</th><th class="num">桥接分</th>
<th class="num">中介中心性</th><th class="num">私聊消息</th></tr></thead><tbody>{context['bridge_rows']}</tbody></table>

<h2>群资源<em>{len(groups)} 个</em></h2>
<table><thead><tr><th>群名</th><th class="num">成员</th><th class="num">消息</th><th class="num">我发</th>
<th class="num">我的占比</th><th class="num">最近</th></tr></thead><tbody>{context['group_rows']}</tbody></table>

<h2>覆盖度<em>按你标注的层级</em></h2>
{context['gap_table']}

<h2>本周该做的几件事<em>自动生成</em></h2>
<table><thead><tr><th class="num">#</th><th>类型</th><th>对象</th><th class="num">沉默</th>
<th>原因</th><th>动作</th></tr></thead><tbody>{context['weekly_rows']}</tbody></table>

<h2>全量名册<em>{stats['persons']} 人</em></h2>
<table><thead><tr><th class="num">#</th><th>姓名</th><th>状态</th><th class="num">消息</th>
<th class="num">我/对方</th><th class="num">我的占比</th><th class="num">会话段</th><th class="num">最近</th>
<th class="num">共同群</th><th class="num">桥接</th><th class="num">强度</th></tr></thead>
<tbody>{context['roster_rows']}</tbody></table>

<footer>
关系强度 = 频率 28% + 近因 30% + 双向均衡 18% + 持续度 12% + 回复速度 12%。<br>
会话段 = 相邻消息间隔 &gt; 6 小时切分。桥接分与中介中心性基于“共同群”图计算。<br>
本页只在本机生成，不含聊天原文、密钥或第三方敏感信息。<br>
生成命令：<code>python scripts/network_report.py --graph data/network/graph.json --output reports/network/dashboard.html</code>
</footer>
</div></body></html>"""


def main():
    parser = argparse.ArgumentParser(description="生成人脉关系 HTML 仪表盘")
    parser.add_argument("--graph", default="data/network/graph.json")
    parser.add_argument("--output", default="reports/network/dashboard.html")
    parser.add_argument("--title", default="人脉地图")
    parser.add_argument("--analysis", help="可选：analysis.json，提供后生成证据版叙事")
    parser.add_argument("--intimacy", help="可选：intimacy.json；默认自动读取 graph 同目录")
    parser.add_argument("--show-quotes", action="store_true", help="报告中显示证据原文（默认隐藏）")
    parser.add_argument("--demo", action="store_true", help="在报告顶部标注“示例数据”")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    analysis = None
    if args.analysis:
        analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    intimacy_path = Path(args.intimacy) if args.intimacy else Path(args.graph).with_name("intimacy.json")
    intimacy = json.loads(intimacy_path.read_text(encoding="utf-8")) if intimacy_path.exists() else None
    rendered = render(graph, title=args.title, analysis=analysis,
                      intimacy=intimacy, show_quotes=args.show_quotes, demo=args.demo)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    manifest = {
        "renderer": "network_report-1.0",
        "graph_messages_digest": graph.get("messages_digest"),
        "analysis_messages_digest": (analysis or {}).get("messages_digest"),
        "analysis_schema": (analysis or {}).get("schema_version"),
        "persons": graph["stats"]["persons"],
        "debt": graph["stats"]["debt"],
        "output": str(output.resolve()),
        "bytes": len(rendered),
    }
    Path(str(output) + ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "output": str(output.resolve()),
        "manifest": str(Path(str(output) + ".manifest.json").resolve()),
        "bytes": len(rendered),
        "persons": graph["stats"]["persons"],
        "debt": graph["stats"]["debt"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
