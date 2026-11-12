# 开源前检查清单

这份文档记录 `renmai`（人脉分析）在合并进本仓库前做过的脱敏处理，方便维护者复查。

## 1. 不会进入版本库的内容

`.gitignore` 已覆盖：

```
data/          # 聊天 bundle、图谱、标注、分析结果
reports/       # HTML 报告、周报、单人档案、深潜结果
vendor/        # 第三方解密器
scripts/tmp/   # 临时脚本与调试输出
*.db
*.json.bak
all_keys.json
```

这些目录只存在于作者本机；`git archive` / `git clone` 都不会包含它们。

## 2. 代码与文档中的示例

- 人名统一使用 `张三 / 甲 / 乙 / 丙` 或 `某某`
- wxid 统一使用 `wxid_xxx` / `wxid_example_*` / `wxid_demo_*`
- 群名统一使用 `某群` / `测试群`
- 公司、机构、政府单位一律抽象为“某公司 / 某机构 / 某区”
- `examples/network/*.json` 全部是虚构数据

## 3. 报告与证据的隐私设计

- 默认不输出聊天原文；只有显式 `--show-quotes` 才显示
- 证据引用只保存 `msg_` ID 与统计字段，不保存整段对话
- 亲密关系候选默认标注“待确认”，不替用户下结论
- 不提供“查人 / 背景调查”能力，不给第三方排名

## 4. 发布前自检

```bash
# 单元测试
python -m unittest discover -s tests -p "test_*.py"

# 隐私扫描（手机号 / 身份证 / 真实 wxid / 消息 ID / 超长数字）
python scripts/privacy_scan.py

# 合成数据全流程（不依赖任何真实聊天）
python scripts/network_demo.py
```

三条都通过再提交。

## 5. 生成干净的发布包

```bash
git archive --format=zip --output=../she-love-me-public.zip HEAD
```

`git archive` 只包含已跟踪文件，天然排除 `data/`、`reports/`、`scripts/tmp/`。

## 6. 已知的不可验证信息

文档与报告里不包含任何真实姓名、公司、职务或关系判断；如需在自己的分析里使用，请写在
`data/network/labels.json`（本机、ignored），不要提交。
