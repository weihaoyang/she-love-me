import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from message_normalizer import normalize_payload  # noqa: E402
from network_evidence import validate  # noqa: E402
from network_report import render  # noqa: E402
from network_viz import render_svg  # noqa: E402

NOW = 1_800_000_000


def msg(sender, content, timestamp):
    return {"sender": sender, "timestamp": timestamp, "type": "text", "content": content}


def write_bundle(root, dirname, username, display, messages):
    folder = Path(root) / dirname
    folder.mkdir(parents=True, exist_ok=True)
    payload = normalize_payload({
        "source": "test",
        "contact_username": username,
        "contact_display": display,
        "own_wxid": "me_wxid",
        "messages": messages,
    })
    (folder / "messages.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def run(script, *args):
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if result.returncode != 0:
        raise AssertionError(f"{script} failed: {result.stderr}\n{result.stdout}")
    return result.stdout


class AnalysisPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.contacts = self.root / "contacts"
        self.output = self.root / "network"
        messages = []
        for day in range(12):
            stamp = NOW - (12 - day) * 86400
            messages.append(msg("me", "合作进展怎么样", stamp))
            messages.append(msg("them", "我这边可以推进", stamp + 60))
        write_bundle(self.contacts, "A__1", "wxid_a", "甲总", messages)
        write_bundle(self.contacts, "B__2", "wxid_b", "乙", [
            msg("them", "在吗", NOW - 100),
        ])
        names = {"contacts": [
            {"username": "wxid_a", "remark": "甲总", "nickname": "甲总"},
            {"username": "wxid_b", "remark": "乙", "nickname": "乙"},
        ]}
        (self.root / "names.json").write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
        labels = {"wxid_a": {"tier": "A10", "role": "投资人", "next": "给一页纸"}}
        (self.root / "labels.json").write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")

        run("network_build.py", "--input", str(self.contacts),
            "--names", str(self.root / "names.json"),
            "--labels", str(self.root / "labels.json"),
            "--output", str(self.output), "--me", "me_wxid", "--now", str(NOW))
        self.graph = json.loads((self.output / "graph.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def analysis_path(self):
        path = self.output / "analysis.json"
        run("network_analyze.py", "--graph", str(self.output / "graph.json"),
            "--output", str(path), "--force", "--top", "2")
        return path

    def test_draft_analysis_is_bound_to_graph(self):
        path = self.analysis_path()
        analysis = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(analysis["messages_digest"], self.graph["messages_digest"])
        self.assertTrue(analysis["relations"])
        result = validate(self.graph, analysis)
        self.assertEqual(result["entries"] > 0, True)

    def test_missing_message_id_fails(self):
        analysis = json.loads(self.analysis_path().read_text(encoding="utf-8"))
        analysis["relations"][0]["evidence_message_ids"] = ["msg_" + "0" * 64]
        with self.assertRaises(ValueError):
            validate(self.graph, analysis)

    def test_quote_mismatch_fails(self):
        analysis = json.loads(self.analysis_path().read_text(encoding="utf-8"))
        person = next(p for p in self.graph["persons"] if p["username"] == "wxid_a")
        payload = json.loads(Path(person["bundle_path"]).read_text(encoding="utf-8-sig"))
        message = payload["messages"][0]
        analysis["relations"][0]["evidence_message_ids"] = [message["message_id"]]
        analysis["relations"][0]["quote"] = "这条消息里没有的话"
        with self.assertRaises(ValueError):
            validate(self.graph, analysis)

    def test_digest_mismatch_fails(self):
        analysis = json.loads(self.analysis_path().read_text(encoding="utf-8"))
        analysis["messages_digest"] = "deadbeef"
        with self.assertRaises(ValueError):
            validate(self.graph, analysis)

    def test_report_renders_thesis_and_hides_quotes(self):
        analysis = json.loads(self.analysis_path().read_text(encoding="utf-8"))
        analysis["thesis"]["headline"] = "这是一句结论"
        html = render(self.graph, analysis=analysis)
        self.assertIn("这是一句结论", html)
        self.assertIn("证据", html)
        self.assertNotIn("<blockquote class=\"q\">", html)

    def test_report_can_show_quotes(self):
        analysis = json.loads(self.analysis_path().read_text(encoding="utf-8"))
        person = next(p for p in self.graph["persons"] if p["username"] == "wxid_a")
        payload = json.loads(Path(person["bundle_path"]).read_text(encoding="utf-8-sig"))
        message = payload["messages"][0]
        analysis["relations"][0]["evidence_message_ids"] = [message["message_id"]]
        analysis["relations"][0]["quote"] = message["content"]
        html = render(self.graph, analysis=analysis, show_quotes=True)
        self.assertIn("合作进展", html)

    def test_network_svg_is_deterministic(self):
        first = render_svg(self.graph)
        second = render_svg(self.graph)
        self.assertEqual(first, second)
        self.assertIn("<svg", first)
        self.assertIn("甲总", first)

    def test_person_page_generates(self):
        out = self.root / "people"
        run("network_person.py", "--graph", str(self.output / "graph.json"),
            "--person", "甲总", "--output", str(out))
        html = (out / "甲总.html").read_text(encoding="utf-8")
        self.assertIn("关系强度", html)
        self.assertIn("共同群", html)
        self.assertIn("甲总", html)


if __name__ == "__main__":
    unittest.main()
