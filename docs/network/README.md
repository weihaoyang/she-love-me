# 人脉分析（Personal Network OS）

把聊天记录变成一张**可执行**的人脉图：谁在你的核心圈、谁在冷却、谁能在群里给你介绍人、这周该找谁说什么。

> 与 `she-love-me` 的区别：那套是“两个人的关系”，这套是“一张网络”。
> 共用同一份聊天 bundle，不需要重新导出。

---

## 先看效果（不需要任何真实数据）

```bash
python scripts/network_demo.py
```

会生成一套合成数据并跑完整流程，打开 `data/network_demo/reports/dashboard.html` 即可看到成品。

---

## 它回答什么问题

- 我有 200 个聊过的人，真正有热度的有多少？
- 哪些关系正在悄悄凉掉？哪些人还欠我一句回复？
- 我认识的人里，谁能把我介绍给另一圈人？
- 我的“资源层”覆盖了几个格子？哪一格是空的？
- 这周我应该主动找哪三个人？

---

## 快速开始

### 一键跑完

```bash
python scripts/network_pipeline.py --input data/contacts --top 10 --deep 3
```

会依次完成：构图 → 亲密候选 → 分析草稿（已有则跳过）→ 仪表盘 → 周报 → 单人档案 → 深潜前 3 个候选。

### 分步执行

### 1. 准备数据（二选一）

**A. 复用已有的 she-love-me 数据**

```bash
ls data/contacts/*/messages.json
```

**B. 从微信重新导出**

按 `she-love-me` 的 `references/data-sources.md` 导出，再用 `convert_weflow_cli.py` 转成 bundle。

### 2. （可选）补名称与群成员

```bash
# 联系人 / 群名称
python scripts/network_names.py --output data/network/names.json

# 群成员（需要 weflow-cli）
weflow-cli contact-schema -n 500 --json > data/network/rooms.json
```

### 3. 构建图谱

```bash
python scripts/network_build.py \
  --input data/contacts \
  --names data/network/names.json \
  --rooms data/network/rooms.json \
  --labels data/network/labels.json \
  --output data/network
```

可选时间窗：加 `--since 2026-01-01` / `--until 2026-06-30`，只统计该区间内的消息。

输出：

- `data/network/graph.json`
- `data/network/persons.csv`

### 4. 生成分析草稿

```bash
python scripts/network_analyze.py \
  --graph data/network/graph.json \
  --output data/network/analysis.json --top 10 --force
```

草稿每句话都由指标推导，但只是起点。

### 5. 补证据并改写

```bash
python scripts/network_context.py --graph data/network/graph.json \
  --person "某人" --keyword "合作" --before 5 --after 5
```

把返回的 `msg_` ID 填进 `analysis.json`，并把 `interpretation` 改成“位置 + 卡点 + 动作”。

### 6. 校验

```bash
python scripts/network_evidence.py --graph data/network/graph.json \
  --analysis data/network/analysis.json
```

### 7. 生成仪表盘

```bash
python scripts/network_report.py \
  --graph data/network/graph.json \
  --analysis data/network/analysis.json \
  --output reports/network/dashboard.html \
  --title "人脉地图"
```

默认隐藏聊天原文；复核时加 `--show-quotes`。

### 8. 每周行动

```bash
python scripts/network_weekly.py --graph data/network/graph.json --limit 6
```

---

## 命令一览

| 命令 | 作用 |
|---|---|
| `network_build.py` | 从 bundle 构图、算指标、导出 CSV |
| `network_pipeline.py` | 一键跑完构图 → 候选 → 分析 → 报告 → 周报 → 档案 |
| `network_analyze.py` | 生成 evidence-oriented 的 `analysis.json` 草稿 |
| `network_context.py` | 按人 + 关键词/消息 ID 补取证据上下文 |
| `network_evidence.py` | 校验证据：消息 ID、原文、统计字段、数据摘要 |
| `network_report.py` | 生成离线 HTML 仪表盘 + 叙事报告 |
| `network_person.py` | 生成单人档案页（`--person` 或 `--top N`） |
| `network_intimacy.py` | 亲密关系候选（结构信号，待确认） |
| `network_deepdive.py` | 用 she-love-me 引擎深潜单段关系 |
| `network_weekly.py` | 生成本周行动清单（Markdown / JSON） |
| `network_ask.py person <名字>` | 看一个人的全部指标 |
| `network_ask.py path <A> <B>` | 找引荐路径 |
| `network_ask.py debt` | 关系债排行 |
| `network_ask.py who <关键词>` | 按身份/群名搜索 |
| `network_ask.py gaps` | 按 labels.tier 统计覆盖度 |
| `network_names.py` | 从 contact.db 还原名称（可选） |
| `network_demo.py` | 生成合成数据并跑通全流程（试用） |

---

## 证据版分析

指标只说明“发生了什么”，分析要说明“这意味着什么”。流程：

```bash
# 1. 草稿
python scripts/network_analyze.py --graph data/network/graph.json \
  --output data/network/analysis.json --top 10 --force

# 2. 取证据（对最重要的人）
python scripts/network_context.py --graph data/network/graph.json \
  --person "某人" --keyword "合作" --before 5 --after 5

# 3. 把 msg_ ID 填进 analysis.json，改写 interpretation

# 4. 校验
python scripts/network_evidence.py --graph data/network/graph.json \
  --analysis data/network/analysis.json

# 5. 出报告
python scripts/network_report.py --graph data/network/graph.json \
  --analysis data/network/analysis.json --output reports/network/dashboard.html
```

规则：

- 关键结论必须带 `evidence_message_ids` 或 `stats_fields`
- `quote` 必须是消息正文的连续片段
- 默认不展示原文；复核时加 `--show-quotes`
- 每次生成报告会写 `dashboard.html.manifest.json`，记录当时的数据摘要，便于复查

---

## 亲密关系层

恋爱是最强的一种“强连接”，所以它是人脉图的一层，而不是另一套系统。

```bash
# 1. 结构信号 → 候选（待你确认）
python scripts/network_intimacy.py --graph data/network/graph.json \
  --output data/network/intimacy.json

# 2. 确认/排除
#    编辑 data/network/intimacy_overrides.json
#    {"wxid_xxx": "confirmed", "wxid_yyy": "excluded"}

# 3. 单段深潜（复用 she-love-me 引擎）
python scripts/network_deepdive.py --person "某人"
```

深潜会生成 `reports/network/deep/<名字>/stats.json`、`chat_history.txt`，
如果提供 `--analysis`，还会生成完整的恋爱分析 `report.html`。

候选信号：深夜占比、强/弱关键词、最长连续天数、媒体占比、双向均衡、共同群折扣。
**这是“值得看一眼”，不是“他们在谈恋爱”**；Agent 不替用户判断感情。

详见 `.agents/skills/renmai/references/intimacy.md`。

---

## 标注：让“资源量级”这条轴有数据

聊天记录能算出**关系强度**，算不出**谁有资源**。后者只能由你提供：

```json
{
  "wxid_xxx": {
    "tier": "A10",
    "role": "某公司创始人",
    "next": "这周给他一页纸"
  }
}
```

字段说明见 `.agents/skills/renmai/references/data-model.md`。

---

## 指标

| 指标 | 含义 |
|---|---|
| 关系强度 0–100 | 频率 28% + 近因 30% + 双向 18% + 持续 12% + 回复速度 12% |
| 会话段 | 间隔 > 6 小时切一段 |
| 关系债 | 最后一条是对方发的，且 ≥3 天 |
| 沉睡资产 | ≥100 条历史消息，90–730 天没动 |
| 桥接分 | 能通过群直接连接到的、你也聊过的人数 |
| 中介中心性 | 在共同群图上的 Brandes betweenness |
| 结构洞约束 | Burt's constraint，越低越像“跨界者” |

完整公式见 `.agents/skills/renmai/references/metrics.md`。

---

## 作为 Agent Skill 使用

```text
$renmai 分析我的人脉，重点看哪些关系在凉
```

Skill 位于 `.agents/skills/renmai/SKILL.md`，会自动执行“构图 → 报告 → 每周行动”。

---

## 和 she-love-me 的关系

```
renmai（人脉 OS）
  ├─ 全量关系图：215 人 / 71 群 / 156k 条
  ├─ 关系债 / 沉睡 / 桥接 / 缺口
  └─ 亲密关系层（候选，需确认）
        └─ she-love-me（单段深潜）
              ├─ stats_analyzer.py
              ├─ build_chat_history.py
              └─ generate_html_report.py
```

- **renmai** 负责“这段关系在整张网里的位置”。
- **she-love-me** 负责“这一段关系内部发生了什么”。
- 两者共用同一份 `data/contacts/` bundle，不需要二次导出。
- 只有用户确认的候选才进入深潜；工具不替用户判断感情。

---

## 隐私

- 全部本地计算，无网络请求。
- 报告不含聊天原文、密钥、手机号。
- `data/`、`reports/` 已在 `.gitignore`。
- 产品定位是“管理你自己的关系”，不提供“查人”能力。

---

## 测试

```bash
python -m unittest discover -s tests -p "test_network_*.py" -v
```
