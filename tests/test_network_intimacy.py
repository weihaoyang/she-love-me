import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from network_intimacy import analyse  # noqa: E402

NOW = 1_800_000_000


def message(sender, text, hour, day=0):
    # 2027-01-15 is a Friday; use UTC+8 semantics via the analyser offset
    base = (NOW // 86400) * 86400
    stamp = base + day * 86400 + (hour - 8) * 3600
    return {"sender": sender, "timestamp": stamp, "type": "text", "content": text,
            "message_id": "msg_" + ("a" * 64)}


def person(**overrides):
    value = {"username": "u", "name": "A", "strength": 85, "mine": 100, "theirs": 100,
             "total": 200, "days_since": 2, "span_days": 60, "group_count": 1}
    value.update(overrides)
    return value


class IntimacyTests(unittest.TestCase):
    def test_late_night_and_strong_keywords_score_high(self):
        messages = []
        for day in range(20):
            messages.append(message("me", "晚安，想你", 23, day))
            messages.append(message("them", "抱抱，我也想你", 0, day + 1))
        result = analyse(person(), messages, min_messages=10)
        self.assertIsNotNone(result)
        self.assertGreater(result["score"], 0.6)
        self.assertGreater(result["signals"]["late_night_ratio"], 0.2)
        self.assertGreater(result["signals"]["strong_hits"], 10)
        self.assertEqual(result["confidence"], "high")

    def test_work_chat_stays_low(self):
        messages = [message("me", "收到，明天发你", 10, day) for day in range(20)]
        result = analyse(person(), messages, min_messages=10)
        self.assertIsNotNone(result)
        self.assertLess(result["score"], 0.5)
        self.assertEqual(result["confidence"], "low")

    def test_short_conversation_is_ignored(self):
        messages = [message("me", "在吗", 12)]
        self.assertIsNone(analyse(person(total=1), messages))

    def test_group_overlap_reduces_score(self):
        messages = []
        for day in range(20):
            messages.append(message("me", "晚安", 23, day))
        low = analyse(person(group_count=1), messages, min_messages=10)
        high = analyse(person(group_count=18), messages, min_messages=10)
        self.assertGreater(low["score"], high["score"])

    def test_evidence_carries_message_ids(self):
        messages = [message("them", "喜欢你", 23, day) for day in range(10)]
        result = analyse(person(), messages, min_messages=10)
        self.assertTrue(result["evidence"])
        self.assertTrue(all(item["message_id"].startswith("msg_") for item in result["evidence"]))


class OverrideTests(unittest.TestCase):
    def test_excluded_candidate_is_dropped(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            bundle.mkdir()
            messages = []
            for day in range(20):
                messages.append(message("me", "晚安", 23, day))
                messages.append(message("them", "抱抱", 0, day + 1))
            (bundle / "messages.json").write_text(json.dumps({
                "contact_username": "u", "contact_display": "A", "messages": messages,
            }, ensure_ascii=False), encoding="utf-8")
            graph = {
                "messages_digest": "x", "generated_at": NOW,
                "persons": [{
                    "username": "u", "name": "A", "kind": "person", "strength": 85,
                    "mine": 100, "theirs": 100, "total": 200, "days_since": 2,
                    "span_days": 60, "group_count": 1, "bundle_path": str(bundle / "messages.json"),
                }],
                "groups": [], "edges": [], "stats": {},
            }
            (root / "graph.json").write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
            (root / "intimacy_overrides.json").write_text(json.dumps({"u": "excluded"}), encoding="utf-8")
            out = root / "intimacy.json"
            subprocess.run([sys.executable, str(REPO_ROOT / "scripts/network_intimacy.py"),
                            "--graph", str(root / "graph.json"), "--output", str(out), "--min-messages", "10"],
                           check=True, capture_output=True, encoding="utf-8")
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["candidates"], [])
            self.assertEqual(payload["excluded"][0]["username"], "u")


if __name__ == "__main__":
    unittest.main()
