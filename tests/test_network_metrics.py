import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import network_metrics as nm  # noqa: E402


def msg(sender, content, timestamp, type_="text"):
    return {"sender": sender, "timestamp": timestamp, "type": type_, "content": content}


class ConversationMetricTests(unittest.TestCase):
    def test_counts_and_balance(self):
        now = 10_000_000
        messages = [msg("me", "在吗", now - 500), msg("them", "在", now - 400)]
        result = nm.conversation_metrics(messages, now=now)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["mine"], 1)
        self.assertEqual(result["theirs"], 1)
        self.assertEqual(result["dominance"], 0.5)
        self.assertEqual(result["sessions"], 1)

    def test_six_hour_gap_starts_new_session(self):
        now = 10_000_000
        messages = [
            msg("me", "早", now - 100_000),
            msg("them", "早", now - 100_000 + 60),
            msg("me", "晚上好", now - 100_000 + 6 * 3600 + 120),
        ]
        result = nm.conversation_metrics(messages, now=now)
        self.assertEqual(result["sessions"], 2)
        self.assertEqual(result["sessions_mine"], 2)

    def test_reply_latency_is_measured_across_roles(self):
        base = 2_000_000
        messages = [
            msg("them", "你好", base),
            msg("me", "你好", base + 30),
            msg("them", "在吗", base + 60),
            msg("me", "在", base + 90),
        ]
        result = nm.conversation_metrics(messages, now=base + 1000)
        self.assertEqual(result["reply_me_n"], 2)
        self.assertEqual(result["reply_me_median"], 30)
        self.assertEqual(result["reply_them_n"], 1)

    def test_ignores_messages_without_timestamp(self):
        result = nm.conversation_metrics(
            [msg("me", "x", None), msg("me", "y", 1_000_000)],
            now=2_000_000,
        )
        self.assertEqual(result["total"], 1)

    def test_empty_returns_none(self):
        self.assertIsNone(nm.conversation_metrics([], now=1))


class ScoringTests(unittest.TestCase):
    def metrics(self, **overrides):
        base = {
            "total": 500, "mine": 250, "theirs": 250, "days_since": 2,
            "active_months": 12, "reply_them_median": 60,
        }
        base.update(overrides)
        return base

    def test_recent_relationship_beats_stale_one(self):
        fresh = nm.score_strength(self.metrics(days_since=1))
        stale = nm.score_strength(self.metrics(days_since=400))
        self.assertGreater(fresh, stale)

    def test_balanced_beats_one_sided(self):
        balanced = nm.score_strength(self.metrics(mine=250, theirs=250))
        one_sided = nm.score_strength(self.metrics(mine=480, theirs=20))
        self.assertGreater(balanced, one_sided)

    def test_strength_is_bounded(self):
        for days in (0, 30, 400):
            value = nm.score_strength(self.metrics(days_since=days))
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 100)

    def test_tier_thresholds(self):
        self.assertEqual(nm.tier_of({"strength": 90, "days_since": 1}), "核心圈")
        self.assertEqual(nm.tier_of({"strength": 70, "days_since": 1}), "活跃层")
        self.assertEqual(nm.tier_of({"strength": 30, "days_since": 200}), "沉睡层")
        self.assertEqual(nm.tier_of({"strength": 30, "days_since": 500}), "失联层")
        self.assertEqual(nm.tier_of({"strength": 30, "days_since": 10}), "外围层")


class TagTests(unittest.TestCase):
    def base(self, **overrides):
        value = {"days_since": 5, "total": 100, "dominance": 0.5, "sessions": 10,
                 "sessions_theirs": 5, "group_count": 1, "strength": 70}
        value.update(overrides)
        return value

    def test_lost_and_cold(self):
        self.assertEqual(nm.tag_of(self.base(days_since=400)), "已失联")
        self.assertEqual(nm.tag_of(self.base(days_since=120)), "已冷却")

    def test_one_sided_detection(self):
        self.assertEqual(nm.tag_of(self.base(dominance=0.9)), "你单方面输出")

    def test_other_side_drives(self):
        self.assertEqual(nm.tag_of(self.base(sessions_theirs=9)), "对方在主动")

    def test_single_contact(self):
        self.assertEqual(nm.tag_of(self.base(total=4)), "一次接触")


class GraphTests(unittest.TestCase):
    def test_co_membership_weights(self):
        membership = {"a": ["g1", "g2"], "b": ["g1"], "c": ["g1", "g2"]}
        edges = nm.build_person_person_edges(membership, {"a", "b", "c"})
        weight = {(e["a"], e["b"]): e["weight"] for e in edges}
        self.assertEqual(weight[("a", "b")], 1)
        self.assertEqual(weight[("a", "c")], 2)
        self.assertEqual(weight[("b", "c")], 1)

    def test_betweenness_finds_the_bridge(self):
        nodes = ["a", "b", "c"]
        adjacency = {"a": {"b": 1}, "b": {"a": 1, "c": 1}, "c": {"b": 1}}
        result = nm.betweenness(nodes, adjacency)
        self.assertGreater(result["b"], result["a"])
        self.assertGreater(result["b"], result["c"])

    def test_constraint_is_bounded(self):
        nodes = ["a", "b", "c"]
        adjacency = {"a": {"b": 1}, "b": {"a": 1, "c": 1}, "c": {"b": 1}}
        result = nm.constraint(nodes, adjacency)
        for value in result.values():
            self.assertGreaterEqual(value, 0)


class WeeklyActionTests(unittest.TestCase):
    def person(self, **overrides):
        value = {"kind": "person", "name": "测试", "username": "u", "total": 500,
                 "days_since": 5, "strength": 80, "last_is_theirs": False,
                 "group_count": 1, "bridge_score": 0}
        value.update(overrides)
        return value

    def test_debt_is_prioritised(self):
        actions = nm.weekly_actions([self.person(last_is_theirs=True, days_since=30)], limit=3)
        self.assertEqual(actions[0]["type"], "关系债")

    def test_dormant_asset_detected(self):
        actions = nm.weekly_actions([self.person(total=800, days_since=200)], limit=3)
        self.assertEqual(actions[0]["type"], "沉睡资产")

    def test_official_accounts_are_skipped(self):
        actions = nm.weekly_actions([self.person(kind="official", last_is_theirs=True)], limit=3)
        self.assertEqual(actions, [])


if __name__ == "__main__":
    unittest.main()
