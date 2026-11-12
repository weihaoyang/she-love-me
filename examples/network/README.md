# 人脉分析示例

```
labels.example.json             # 人工标注模板（资源量级 + 身份 + 下一步）
intimacy_overrides.example.json # 亲密关系候选的确认 / 排除
```

用法：

```bash
python scripts/network_build.py --input data/contacts \
  --names data/network/names.json \
  --rooms data/network/rooms.json \
  --labels examples/network/labels.example.json \
  --output data/network
```

真实使用时请复制一份到 `data/network/labels.json` 再改，不要提交到仓库。
