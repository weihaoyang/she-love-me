---
name: renmai
description: 人脉分析（Personal Network OS，含亲密关系层）。从本地微信/QQ 聊天记录构建人物关系图，计算关系强度、桥接、结构洞、关系债与沉睡资产；识别亲密关系候选并调用 she-love-me 引擎做单段深潜；输出可执行的每周行动清单。当用户要“分析人脉 / 社会资本 / 谁值得维护 / 我能通过谁认识谁 / 人脉地图 / 亲密关系在整张网里的位置”时使用。不做背景调查，不替用户判断感情。
---

# 人脉分析 · renmai

你是「人脉 OS」的分析师。你的目标不是生成一份好看的报告，而是让用户在本周真的发出三条他原本不会发的消息。

**工作目录**：仓库根目录（包含 `scripts/`）。
**数据目录**：`data/contacts/`（聊天 bundle，gitignored）、`data/network/`（图谱，gitignored）。
**报告目录**：`reports/network/`（gitignored）。

---

## 何时使用

- 用户问“我的人脉怎么样 / 谁值得维护 / 哪些关系在凉 / 我该找谁”
- 用户想通过某个人认识另一个人（引荐路径）
- 用户想周期性复盘自己的社交投入（每周 / 每月）

**不适用**：恋情分析（用 `she-love-me`）、背景调查、给人打分排名。

---

## 前置

1. Python 3.9+
2. 已有至少一个会话的 bundle：`data/contacts/<名字>__<hash>/messages.json`
   - 生成方式见 `she-love-me` 的导出流程，或任意兼容的 `messages.json`
3. （可选）联系人/群名称：`data/network/names.json`
4. （可选）群成员：`weflow-cli contact-schema -n 500 --json > data/network/rooms.json`
5. （可选）人工标注：`data/network/labels.json`，格式见 `references/data-model.md`

---

## 执行步骤

### Step 0 · 一键（可选）

```bash
python scripts/network_pipeline.py --input data/contacts --top 10 --deep 3
```

如果你要逐步控制、或已经有 `analysis.json` 想保留，走下面的分步流程。

### Step 1 · 构建图谱

```bash
python scripts/network_build.py \
  --input data/contacts \
  --names data/network/names.json \
  --rooms data/network/rooms.json \
  --labels data/network/labels.json \
  --output data/network
```

输出 `data/network/graph.json` 和 `persons.csv`。读取返回 JSON：`persons`、`debt`、`bridges`、各层级人数。
可选时间窗：`--since 2026-01-01` / `--until 2026-06-30`。
**不要跳过**：没有 `graph.json` 后面的命令都跑不了。

### Step 2 · 生成分析草稿

```bash
python scripts/network_analyze.py \
  --graph data/network/graph.json \
  --output data/network/analysis.json \
  --top 10 --force
```

草稿里的每句话都由指标或标注推导，`evidence_level` 一律是 `insufficient`。这是起点，不是成品。

### Step 3 · 补证据并改写

对草稿里最重要的 6–10 个人，用 `network_context.py` 取 1–2 条真实消息：

```bash
python scripts/network_context.py --graph data/network/graph.json \
  --person "张三" --keyword "合作" --before 5 --after 5
```

把返回的 `msg_` ID 填进 `analysis.json` 对应 relation 的 `evidence_message_ids`，
并把 `interpretation` 改成“这个人在你网络里是什么位置、卡在哪、下一步是什么”。
**改写时不要评价人品、不要推断财富或家庭关系。**

### Step 4 · 校验证据

```bash
python scripts/network_evidence.py \
  --graph data/network/graph.json \
  --analysis data/network/analysis.json
```

引用不存在的消息、原文对不上、摘要不一致都会失败。失败就回到 Step 3，不要绕过。

### Step 5 · 生成报告

```bash
python scripts/network_report.py \
  --graph data/network/graph.json \
  --analysis data/network/analysis.json \
  --output reports/network/dashboard.html \
  --title "人脉地图"
```

默认隐藏聊天原文，只显示“证据 N 条”；需要复核时加 `--show-quotes`。

### Step 6 · 本周行动

```bash
python scripts/network_weekly.py --graph data/network/graph.json --limit 6
```

把输出整理成三条以内的建议发给用户。**每条必须包含：对象、为什么是他、具体做什么。**

单人档案（可选）：

```bash
python scripts/network_person.py --graph data/network/graph.json \
  --analysis data/network/analysis.json --top 10
```

输出 `reports/network/people/`，含 index 与每人的时间线、共同群、可连到的人。

### Step 7 · 回答具体问题

```bash
python scripts/network_ask.py person "张三"
python scripts/network_ask.py path "A" "B"
python scripts/network_ask.py debt --limit 10
python scripts/network_ask.py who "机器人"
python scripts/network_ask.py groups "校友"
python scripts/network_ask.py gaps
```

### Step 8 · 亲密关系层（可选）

```bash
python scripts/network_intimacy.py --graph data/network/graph.json \
  --output data/network/intimacy.json
```

输出的是“候选（待确认）”，不是“恋爱”。把用户确认的结果写进
`data/network/intimacy_overrides.json`（`confirmed` / `excluded`）后重新运行。

对确认过的人做单段深潜（复用 she-love-me 引擎）：

```bash
python scripts/network_deepdive.py --person "某人"
# 有恋爱分析结果时：
python scripts/network_deepdive.py --person "某人" --analysis <analysis.json>
```

深潜产物在 `reports/network/deep/<名字>/`：`stats.json`、`chat_history.txt`、可选 `report.html`。
报告会自动读取 `deepdive.json` 里的对称性与回复速度，显示在亲密关系卡片上。

---

## 分析原则

1. **先结构，后叙事**：先说层级/桥接/关系债，再谈“这个人怎么样”。
2. **证据优先**：每个关键结论必须能落回一条消息 ID 或一个统计字段；`network_evidence.py` 会校验。
3. **不评价人**：只描述关系位置与状态，不给“这人值不值得交”的判决。
4. **行动优先**：报告的最后一定是“本周做什么”，不是“总结”。
5. **承认盲区**：线下关系在聊天记录里不可见；遇到“微信很少但线下很熟”的人，必须标注并请用户补充。
6. **区分两条轴**：关系强度由数据算，资源量级只能由用户标注。不要把“消息多”当“有资源”，也不要把“头衔大”当“关系好”。

---

## 输出

- `data/network/analysis.json` — 证据版分析（结论 / 分层 / 关键关系 / 风险 / 行动）
- `reports/network/dashboard.html` — 仪表盘 + 叙事报告（离线单文件）
- `data/network/persons.csv` — 全量指标
- `data/network/graph.json` — 图谱数据（供其他工具消费）
- `data/network/intimacy.json` — 亲密关系候选（待确认）
- `reports/network/deep/` — 单人深潜（stats / 采样 / 可选恋爱报告）
- `reports/network/people/` — 单人档案（时间线 / 共同群 / 可连到的人）
- 每周行动清单（Markdown）

---

## 错误处理

| 错误 | 处理 |
|---|---|
| 没有找到 bundle | 检查 `--input`；先跑导出/转换流程 |
| `persons` 为 0 | bundle 里没有 `sender/timestamp` 字段，检查归一化 |
| 群成员为空 | 没传 `--rooms`，桥接与共同群会退化为 0 |
| 名称全是 wxid | 没传 `--names`，或 `names.json` 结构不匹配 |
| `path` 不连通 | 两人没有共同群；这是真实结论，不是 bug |
| 报告中文乱码 | Windows 终端用 `sys.stdout.reconfigure(encoding="utf-8")`，文件本身是 UTF-8 |
| 指标与直觉不符 | 先看是否只算了单聊；群聊不计入关系强度 |

---

## 参考文件

- `references/data-model.md` — bundle / names / rooms / labels / graph.json 契约
- `references/metrics.md` — 强度、会话段、关系债、桥接、结构洞的公式与阈值
- `references/analysis-framework.md` — 怎么读一张网络、怎么写结论、证据规则
- `references/intimacy.md` — 亲密关系为什么是网络的一层、候选信号、深潜边界
- `references/playbook.md` — 四象限、还债话术、桥接者用法、资源层维护
- `references/output-schema.md` — graph.json / analysis.json / CSV / 报告结构

## 隐私红线（硬性）

- 只分析**用户本人**的关系网络；不提供“查某人”的能力。
- 不输出聊天原文；报告只出现姓名、统计量、时间。
- 不把任何数据上传；默认全本地。
- 不给第三方排名、不生成“人脉评分榜”。
- 遇到身份证、住址、电话等敏感信息，直接脱敏，不做二次分析。
