# AGENTS.md

## Repository Focus

- This repository packages the `she-love-me` workflow for analyzing WeChat or QQ chat histories and generating an HTML relationship report.
- It also supports optional WeChat emoji export: `messages.json` can include emoji metadata, and `scripts/export_emojis.py` can download/store emoji assets and generate `reports/emojis_preview.html`.
- Current preferred export layout is per-contact bundles under `data/contacts/<联系人>__<hash>/`, where chat records and emoji records are separated but linked (`messages.json` + `emojis.json`).
- The unified skill entrypoint for all tools is `.agents/skills/she-love-me/SKILL.md` (Claude Code, OpenClaw, Codex, Cursor, Copilot, Gemini CLI).
- Analysis and data-source knowledge is split across `references/` under that directory; SKILL.md is the control plane.
- For a new Windows WeChat user, agents should execute the full `weflow-cli` setup/export path in `references/data-sources.md`, including requesting required install/network/admin approvals. CipherTalk CLI and its official desktop MCP are the automatic fallbacks.

## 人脉分析（renmai）

- 入口：`.agents/skills/renmai/SKILL.md`（第二个 Agent Skill，与恋爱分析并列）。
- 数据：直接复用 `data/contacts/<名字>__<hash>/messages.json`，不需要重新导出。
- 命令：`scripts/network_build.py` → `network_report.py` → `network_weekly.py`；查询用 `network_ask.py`。
- 产物：`data/network/graph.json`、`data/network/persons.csv`、`reports/network/dashboard.html`。
- 标注：`data/network/labels.json` 提供“资源量级”这条人工轴，模板见 `examples/network/labels.example.json`。
- 边界：只分析本人的关系网络；不做背景调查、不给人排名、不输出聊天原文。

## Codex Guidance

- When a user asks to analyze chat logs with this project, prefer the repo skill `she-love-me`.
- Keep the working directory at the repository root when following the skill workflow.
- Keep generated or sensitive outputs under `vendor/`, `data/`, and `reports/`; do not move personal chat data into tracked files.
- If the user asks about stickers/emojis, use the selected contact bundle's `messages_path`, then run `scripts/export_emojis.py`.
- Prefer `--output-dir data/contacts` over a shared `data/messages.json` whenever exporting a specific contact, so different users do not overwrite each other.
- Do not stop at giving setup commands when the user asks for analysis. Run environment checks, install the selected exporter, initialize it, export JSON, convert it, and continue to the report; pause only for login, approval, token, or contact selection.
- If the user wants to invoke the skill explicitly in Codex, they can mention `$she-love-me`.
