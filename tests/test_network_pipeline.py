import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
NOW = 1_800_000_000


def write_bundle(root, dirname, username, display, messages):
    folder = Path(root) / dirname
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "test",
        "contact_username": username,
        "contact_display": display,
        "own_wxid": "me_wxid",
        "messages": messages,
    }
    (folder / "messages.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def msg(sender, content, timestamp):
    return {"sender": sender, "timestamp": timestamp, "type": "text", "content": content}


def run(script, *args):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(f"{script} failed: {result.stderr}\n{result.stdout}")
    return result.stdout


class NetworkPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.contacts = self.root / "contacts"
        self.output = self.root / "network"

        a_messages = []
        for day in range(10):
            stamp = NOW - (10 - day) * 86400
            a_messages.append(msg("me", f"a{day}", stamp))
            a_messages.append(msg("them", f"b{day}", stamp + 60))
        write_bundle(self.contacts, "A__1", "wxid_a", "甲", a_messages)

        write_bundle(self.contacts, "B__2", "wxid_b", "乙", [
            msg("them", "hi", NOW - 100),
            msg("me", "hello", NOW - 90),
        ])
        write_bundle(self.contacts, "G__3", "123@chatroom", "测试群", [
            msg("them", "群里说话", NOW - 200),
            msg("me", "收到", NOW - 190),
        ])

        names = {
            "contacts": [
                {"username": "wxid_a", "remark": "甲总", "nickname": "甲"},
                {"username": "wxid_b", "remark": "", "nickname": "乙"},
                {"username": "123@chatroom", "remark": "", "nickname": "测试群"},
            ],
            "rooms": {"123@chatroom": "测试群"},
        }
        (self.root / "names.json").write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")

        rooms = {"rooms": [{
            "username": "123@chatroom", "owner": "me_wxid", "memberCount": 3,
            "members": [
                {"userName": "me_wxid", "displayName": "我"},
                {"userName": "wxid_a", "displayName": "甲"},
                {"userName": "wxid_b", "displayName": "乙"},
            ],
        }]}
        (self.root / "rooms.json").write_text(json.dumps(rooms, ensure_ascii=False), encoding="utf-8")

        labels = {"wxid_a": {"tier": "A10", "role": "投资人", "next": "给一页纸"}}
        (self.root / "labels.json").write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        run("network_build.py", "--input", str(self.contacts),
            "--names", str(self.root / "names.json"),
            "--rooms", str(self.root / "rooms.json"),
            "--labels", str(self.root / "labels.json"),
            "--output", str(self.output), "--me", "me_wxid", "--now", str(NOW))
        return json.loads((self.output / "graph.json").read_text(encoding="utf-8"))

    def test_build_produces_expected_graph(self):
        graph = self.build()
        self.assertEqual(graph["stats"]["persons"], 2)
        self.assertEqual(len(graph["groups"]), 1)
        persons = {p["username"]: p for p in graph["persons"] if p["kind"] == "person"}
        self.assertEqual(persons["wxid_a"]["name"], "甲总")
        self.assertEqual(persons["wxid_a"]["group_count"], 1)
        self.assertEqual(persons["wxid_a"]["label"]["tier"], "A10")
        self.assertEqual(len(graph["edges"]), 1)
        self.assertEqual(graph["edges"][0]["weight"], 1)
        self.assertTrue((self.output / "persons.csv").exists())

    def test_report_and_weekly_consume_graph(self):
        self.build()
        report = self.root / "dashboard.html"
        run("network_report.py", "--graph", str(self.output / "graph.json"),
            "--output", str(report), "--title", "测试人脉")
        html = report.read_text(encoding="utf-8")
        self.assertIn("测试人脉", html)
        self.assertIn("甲总", html)
        self.assertIn("关系债", html)
        self.assertTrue(Path(str(report) + ".manifest.json").exists())

        weekly = run("network_weekly.py", "--graph", str(self.output / "graph.json"),
                     "--json", "--limit", "3")
        actions = json.loads(weekly)
        self.assertIsInstance(actions, list)

    def test_ask_person_and_path(self):
        self.build()
        person = run("network_ask.py", "person", "甲总", "--graph", str(self.output / "graph.json"))
        self.assertIn("甲总", person)
        path = run("network_ask.py", "path", "甲总", "乙", "--graph", str(self.output / "graph.json"))
        self.assertIn("路径", path)


if __name__ == "__main__":
    unittest.main()
