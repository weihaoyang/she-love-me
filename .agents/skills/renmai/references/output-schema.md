# 输出结构

## graph.json

```jsonc
{
  "schema_version": "1.0",
  "generated_at": 1762900000,          // epoch 秒
  "me": {"username": "wxid_xxx", "name": "我"},
  "window": {"first": 1718400000, "last": 1762900000},
  "stats": {
    "persons": 215,                    // 有私聊的人
    "groups": 64,                      // 共同群数量（去重）
    "total_messages": 155928,
    "core": 10, "active": 48, "dormant": 52, "lost": 35, "peripheral": 70,
    "debt": 118,
    "bridges": 116
  },
  "series": [["2024-06", 120], ["2024-07", 340]],   // 每月私聊消息数
  "persons": [
    {
      "username": "wxid_xxx",
      "name": "张三",
      "kind": "person",                // person / group / official
      "total": 500, "mine": 250, "theirs": 250,
      "first": 1718400000, "last": 1762900000,
      "span_days": 500.0, "days_since": 2.0,
      "active_months": 12, "active_days": 80,
      "sessions": 40, "sessions_mine": 15, "sessions_theirs": 25,
      "reply_me_median": 30, "reply_them_median": 60,
      "reply_me_n": 30, "reply_them_n": 28,
      "types": {"text": 490, "image": 10},
      "last_is_theirs": false,
      "last30": 20, "prev30": 15, "momentum": 5,
      "dominance": 0.5, "my_daily": 3.1,
      "strength": 78.5,
      "tier": "活跃层",
      "tag": "稳定双向",
      "shared_groups": ["某群"],
      "group_count": 3,
      "degree": 5, "betweenness": 0.0123, "community": 2,
      "constraint": 0.31, "bridge_score": 7,
      "label": {"tier": "A10", "role": "…", "next": "…"}   // 可选
    }
  ],
  "groups": [
    {
      "username": "123@chatroom", "name": "某群", "kind": "group",
      "member_count": 182, "owner": "wxid_owner", "owner_name": "群主",
      "i_am_owner": false,
      "member_usernames": ["wxid_a", "wxid_b"],
      "total": 5000, "mine": 120, "days_since": 0.5,
      "tier": "活跃层", "tag": "对方在主动"
    }
  ],
  "edges": [
    {"a": "wxid_a", "b": "wxid_b", "weight": 2}
  ],
  "graph": {
    "degree": {"wxid_a": 5},
    "betweenness": {"wxid_a": 0.0123},
    "community": {"wxid_a": 2},
    "constraint": {"wxid_a": 0.31}
  }
}
```

## analysis.json

```jsonc
{
  "schema_version": "1.0",
  "messages_digest": "与 graph.json 一致",   // 必填，否则校验失败
  "prompt_version": "network-1.0",
  "model": "实际使用的模型或 null",
  "thesis": {
    "headline": "一句判断",
    "summary": "3-5 句",
    "evidence_level": "medium",
    "evidence_message_ids": ["msg_..."],
    "stats_fields": ["stats.core", "stats.debt"]
  },
  "layers": [
    {"name": "核心圈", "count": 10, "reading": "...",
     "evidence_level": "low", "evidence_message_ids": [], "stats_fields": ["stats.core"]}
  ],
  "relations": [
    {"username": "wxid_x", "name": "张三", "role": "身份",
     "state": "高投入 · 高资源", "interpretation": "位置 + 卡点",
     "next_action": "一句可执行的动作",
     "evidence_level": "medium",
     "evidence_message_ids": ["msg_..."],
     "stats_fields": ["person.wxid_x.total", "person.wxid_x.days_since"]}
  ],
  "risks": [
    {"type": "集中度", "reading": "...", "evidence_level": "low",
     "evidence_message_ids": [], "stats_fields": ["stats.total_messages"]}
  ],
  "actions": [
    {"type": "关系债", "name": "张三", "username": "wxid_x", "days": 25,
     "reason": "...", "action": "...", "evidence_level": "insufficient",
     "evidence_message_ids": [], "stats_fields": ["person.wxid_x.days_since"]}
  ]
}
```

校验规则（`network_evidence.py`）：

- `messages_digest` 必须等于当前 `graph.json.messages_digest`
- 每个 `evidence_message_ids` 必须存在于对应人的 bundle
- `quote`（如有）必须是引用消息正文的连续片段
- 每个 `stats_fields` 必须能解析且非空（中高等级证据）
- 递归检查：任何含 `evidence_message_ids` 或 `stats_fields` 的对象都会被校验

## persons.csv

UTF-8 with BOM（Excel 直接打开不乱码）。列：

`姓名, username, 类型, 层级, 强度, 消息, 我发, 对方发, 我的占比, 会话段, 最近(天), 共同群, 桥接分, 中介中心性, 约束指数, 标签, 圈层标注, 身份`

## 仪表盘

`reports/network/dashboard.html`，单文件、离线、无外部依赖。章节：

1. 结构诊断（自动生成的自然语言结论）
2. 月度时间线
3. 核心圈 / 活跃层
4. 关系债
5. 沉睡资产
6. 桥接者
7. 群资源
8. 覆盖度（按 labels.tier）
9. 本周行动
10. 全量名册

## 每周清单

`network_weekly.py` 输出 Markdown；`--json` 输出可直接被其他工具消费的数组：

```json
[
  {
    "type": "关系债",
    "priority": 12.3,
    "name": "张三",
    "username": "wxid_xxx",
    "days": 25,
    "reason": "最后一条是对方发的，已 25 天",
    "action": "回一条具体的话，别只回“在”"
  }
]
```
