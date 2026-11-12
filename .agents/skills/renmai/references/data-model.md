# 数据模型

## 1. 会话 bundle

每个联系人一个目录：

```
data/contacts/<名字>__<hash>/
  messages.json      # 必需
  imports/           # 导入历史（由 bundle_store 维护）
```

`messages.json` 的关键字段（由 `message_normalizer.py` 统一）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `source` | str | 来源：weflow-cli / ciphertalk / markdown |
| `contact_username` | str | 对方 wxid 或群 `xxx@chatroom` |
| `contact_display` | str | 显示名 |
| `own_wxid` | str | 自己的 wxid |
| `messages[]` | list | 归一化后的消息 |
| `messages[].sender` | `me` / `them` | 方向 |
| `messages[].timestamp` | int | Unix 秒 |
| `messages[].type` | str | text / image / voice / emoji / system … |
| `messages[].content` | str | 文本或占位符 |
| `messages[].message_id` | str | 稳定 ID，用于增量去重 |
| `messages[].transcript` | str? | 语音转写（可选） |

群聊 bundle 的 `contact_username` 以 `@chatroom` 结尾，`sender` 仍只有 me/them——群内其他人的身份需要从原始导出或群成员表补。

## 2. names.json（可选）

两种形态都支持：

```json
{
  "contacts": [
    {"username": "wxid_xxx", "remark": "备注名", "nickname": "微信昵称"}
  ],
  "rooms": {"123@chatroom": "群名"}
}
```

```json
{"wxid_xxx": {"remark": "备注名", "nickname": "昵称"}}
```

生产环境的 `names.json` 可以从 `contact.db` 还原（`remark` 优先于 `nick_name`）。

## 3. rooms.json（可选）

`weflow-cli contact-schema -n 500 --json` 的原始输出即可：

```json
{
  "rooms": [
    {
      "username": "123@chatroom",
      "owner": "wxid_owner",
      "memberCount": 182,
      "members": [
        {"userName": "wxid_a", "displayName": "甲", "inviter": "wxid_owner"}
      ]
    }
  ]
}
```

也接受简化形态：

```json
{"123@chatroom": ["wxid_a", "wxid_b"]}
```

## 4. labels.json（可选，但强烈建议）

人工标注是“资源量级”这条轴的唯一来源。聊天记录能算出关系强度，算不出谁有钱、谁有决策权。

```json
{
  "wxid_xxx": {
    "tier": "A10",
    "role": "某公司创始人 / 某机构负责人",
    "next": "这周该做的具体动作"
  }
}
```

约定：

- `tier`：自由文本，但要保持有限枚举（如 `A10` / `A10+` / `机构` / `产业` / `学术` / `组织` / `待定`）。仪表盘的“覆盖度”按它分组。
- `role`：公开身份或你对他的定位，不要写聊天内容。
- `next`：一句话动作，必须可执行。

**标注只能由用户本人提供**；Agent 不得凭聊天内容推断财富、职务或家庭关系。

## 5. graph.json

见 `output-schema.md`。
