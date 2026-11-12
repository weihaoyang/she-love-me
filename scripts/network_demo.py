"""Generate a synthetic demo network and run the whole pipeline.

No private data is used. Useful for trying the tool, screenshots and tests.

    python scripts/network_demo.py
    python scripts/network_demo.py --output data/network_demo
"""

import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
NOW = int(datetime(2026, 11, 12, tzinfo=timezone.utc).timestamp())

PEOPLE = [
    ("wxid_demo_founder", "创始人 A", 900, 2, ["资本"]),
    ("wxid_demo_vc", "投资人 B", 120, 40, ["资本"]),
    ("wxid_demo_prof", "教授 C", 260, 5, ["学术"]),
    ("wxid_demo_peer", "合伙人 D", 1800, 1, ["组织"]),
    ("wxid_demo_supplier", "供应链 E", 80, 25, ["产业"]),
    ("wxid_demo_dormant", "旧友 F", 700, 160, ["生活"]),
    ("wxid_demo_debt", "客户 G", 300, 22, ["产业"]),
    ("wxid_demo_new", "新人 H", 6, 1, ["待定"]),
    ("wxid_demo_lawyer", "律师 I", 40, 60, ["服务"]),
    ("wxid_demo_doctor", "医生 J", 18, 120, ["服务"]),
    ("wxid_demo_media", "记者 K", 25, 80, ["媒体"]),
    ("wxid_demo_alumni", "校友 L", 210, 12, ["组织"]),
    ("wxid_demo_intern", "实习生 M", 160, 3, ["组织"]),
    ("wxid_demo_designer", "设计师 N", 95, 18, ["产业"]),
    ("wxid_demo_ops", "运营 O", 320, 4, ["组织"]),
    ("wxid_demo_pm", "产品 P", 280, 7, ["组织"]),
    ("wxid_demo_dev", "研发 Q", 190, 9, ["组织"]),
    ("wxid_demo_finance", "财务 R", 55, 45, ["服务"]),
    ("wxid_demo_client2", "客户 S", 130, 30, ["产业"]),
    ("wxid_demo_mentor", "导师 T", 75, 90, ["学术"]),
]

GROUPS = {
    "1001@chatroom": ("创业营", "wxid_demo_founder",
                      ["wxid_demo_founder", "wxid_demo_vc", "wxid_demo_supplier",
                       "wxid_demo_alumni", "wxid_demo_ops"]),
    "1002@chatroom": ("实验室", "wxid_demo_prof",
                      ["wxid_demo_prof", "wxid_demo_peer", "wxid_demo_intern", "wxid_demo_mentor"]),
    "1003@chatroom": ("行业群", "wxid_demo_supplier",
                      ["wxid_demo_supplier", "wxid_demo_debt", "wxid_demo_founder",
                       "wxid_demo_client2", "wxid_demo_designer"]),
    "1004@chatroom": ("项目组", "wxid_demo_peer",
                      ["wxid_demo_peer", "wxid_demo_pm", "wxid_demo_dev",
                       "wxid_demo_ops", "wxid_demo_designer"]),
    "1005@chatroom": ("校友会", "wxid_demo_alumni",
                      ["wxid_demo_alumni", "wxid_demo_founder", "wxid_demo_media",
                       "wxid_demo_mentor", "wxid_demo_vc"]),
    "1006@chatroom": ("供应链", "wxid_demo_supplier",
                      ["wxid_demo_supplier", "wxid_demo_finance", "wxid_demo_client2",
                       "wxid_demo_lawyer"]),
}


def write_bundle(root, username, display, total, days_ago, messages):
    suffix = hashlib.md5(username.encode("utf-8")).hexdigest()[:4]
    folder = root / f"{display}__{suffix}"
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "demo",
        "contact_username": username,
        "contact_display": display,
        "own_wxid": "wxid_me",
        "messages": messages,
    }
    (folder / "messages.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def conversation(total, days_ago, last_theirs, seed):
    random.seed(seed)
    span = 365 * 86400
    end = NOW - days_ago * 86400
    start = end - span
    step = span / max(total, 1)
    messages = []
    for index in range(total):
        sender = "me" if index % 2 == 0 else "them"
        stamp = int(start + index * step + random.randint(0, 600))
        messages.append({"sender": sender, "timestamp": stamp, "type": "text", "content": f"m{index}"})
    if last_theirs:
        messages.append({"sender": "them", "timestamp": end, "type": "text", "content": "在吗"})
    return messages


def run(script, *args):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise SystemExit(f"{script} 失败:\n{result.stderr}\n{result.stdout}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description="生成可运行的示例人脉网络")
    parser.add_argument("--output", default="data/network_demo")
    args = parser.parse_args()
    base = Path(args.output)
    contacts = base / "contacts"
    network = base / "network"
    reports = base / "reports"
    for folder in (network, reports):
        folder.mkdir(parents=True, exist_ok=True)
    if contacts.exists():
        shutil.rmtree(contacts)
    contacts.mkdir(parents=True, exist_ok=True)

    for index, (username, display, total, days, _) in enumerate(PEOPLE):
        write_bundle(contacts, username, display, total, days,
                     conversation(total, days, last_theirs=(index % 3 == 0), seed=index))

    for group_id, (name, owner, members) in GROUPS.items():
        messages = conversation(40, 10, last_theirs=False, seed=hash(group_id) % 1000)
        write_bundle(contacts, group_id, name, 40, 10, messages)

    names = {
        "contacts": [{"username": u, "remark": d, "nickname": d} for u, d, *_ in PEOPLE]
                    + [{"username": g, "remark": v[0], "nickname": v[0]} for g, v in GROUPS.items()],
        "rooms": {g: v[0] for g, v in GROUPS.items()},
    }
    (base / "names.json").write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")

    rooms = {"rooms": [
        {"username": g, "owner": owner, "memberCount": len(members) + 1,
         "members": [{"userName": "wxid_me"}] + [{"userName": m} for m in members]}
        for g, (name, owner, members) in GROUPS.items()
    ]}
    (base / "rooms.json").write_text(json.dumps(rooms, ensure_ascii=False), encoding="utf-8")

    labels = {
        "wxid_demo_founder": {"tier": "A10", "role": "某机器人公司创始人", "next": "发一页纸，约一次判断"},
        "wxid_demo_vc": {"tier": "A10+", "role": "早期基金合伙人", "next": "请他 judge，并要一个引荐"},
        "wxid_demo_prof": {"tier": "学术", "role": "高校副教授", "next": "把技术叙事交给他看"},
        "wxid_demo_supplier": {"tier": "产业", "role": "供应链技术负责人", "next": "一个具体的适配问题"},
        "wxid_demo_debt": {"tier": "产业", "role": "客户", "next": "回一条具体的话"},
        "wxid_demo_lawyer": {"tier": "服务", "role": "执业律师", "next": "把合同模板过一遍"},
        "wxid_demo_media": {"tier": "媒体", "role": "科技记者", "next": "给一个可报道的进展"},
        "wxid_demo_alumni": {"tier": "组织", "role": "校友会理事", "next": "请他引荐一位校友"},
        "wxid_demo_mentor": {"tier": "学术", "role": "产业导师", "next": "季度汇报一次"},
        "wxid_demo_client2": {"tier": "产业", "role": "潜在客户", "next": "约一次场景演示"},
    }
    (base / "labels.json").write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")

    run("network_build.py", "--input", str(contacts), "--names", str(base / "names.json"),
        "--rooms", str(base / "rooms.json"), "--labels", str(base / "labels.json"),
        "--output", str(network), "--me", "wxid_me", "--now", str(NOW))
    run("network_report.py", "--graph", str(network / "graph.json"),
        "--output", str(reports / "dashboard.html"), "--title", "示例人脉地图", "--demo")
    weekly = run("network_weekly.py", "--graph", str(network / "graph.json"), "--limit", "5")

    print(json.dumps({
        "status": "ok",
        "dashboard": str((reports / "dashboard.html").resolve()),
        "graph": str((network / "graph.json").resolve()),
        "weekly_preview": weekly.strip().splitlines()[:6],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
