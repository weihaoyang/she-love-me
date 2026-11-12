"""Export contact and group names from the local WeChat contact.db.

Optional helper for the network pipeline. It reads the encrypted database
read-only through weflow-cli's own decryptor, and never prints or stores the key.

    python scripts/network_names.py --output data/network/names.json

If weflow-cli is not installed, pass its scripts directory explicitly:

    python scripts/network_names.py --weflow-scripts "C:/Users/me/AppData/Roaming/npm/node_modules/weflow-cli/scripts"
"""

import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def find_weflow_scripts(explicit=None):
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "npm" / "node_modules" / "weflow-cli" / "scripts")
    home = Path.home()
    candidates.append(home / ".npm-global" / "lib" / "node_modules" / "weflow-cli" / "scripts")
    candidates.append(Path("/usr/local/lib/node_modules/weflow-cli/scripts"))
    candidates.append(Path("/usr/lib/node_modules/weflow-cli/scripts"))
    for candidate in candidates:
        if (candidate / "_utils.py").exists():
            return candidate
    return None


def load_rows():
    if WEFLOW_SCRIPTS:
        sys.path.insert(0, str(WEFLOW_SCRIPTS))
        sys.path.insert(0, str(WEFLOW_SCRIPTS.parent))
    try:
        from _utils import get_db_config  # noqa: PLC0415
        from nt_decrypt import connect_encrypted_readonly  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on local install
        raise SystemExit(
            "找不到 weflow-cli 的解密模块。请用 --weflow-scripts 指定 "
            "weflow-cli/scripts 目录，或手动准备 names.json。"
        ) from exc

    config = get_db_config()
    database = config.get("contact_db")
    key = config.get("contact_key")
    salt = config.get("contact_salt")
    if not database or not Path(database).exists():
        raise SystemExit("contact.db 不存在；先在 weflow-cli 里完成 init。")
    if not key or not salt:
        raise SystemExit("contact.db 密钥未配置；先运行 weflow-cli init。")

    result = connect_encrypted_readonly(database, "x'%s%s'" % (key, salt))
    connection = result[0] if isinstance(result, tuple) else result
    cursor = connection.cursor()
    cursor.execute(
        "SELECT username, alias, remark, nick_name, local_type FROM contact"
    )
    rows = cursor.fetchall()
    connection.close()
    return rows


WEFLOW_SCRIPTS = None


def main():
    global WEFLOW_SCRIPTS
    parser = argparse.ArgumentParser(description="从 contact.db 还原联系人与群名称")
    parser.add_argument("--output", default="data/network/names.json")
    parser.add_argument("--weflow-scripts", help="weflow-cli/scripts 目录")
    args = parser.parse_args()
    WEFLOW_SCRIPTS = find_weflow_scripts(args.weflow_scripts)
    if not WEFLOW_SCRIPTS:
        raise SystemExit("找不到 weflow-cli/scripts；请用 --weflow-scripts 指定。")

    rows = load_rows()
    contacts, rooms = [], {}
    for username, alias, remark, nickname, local_type in rows:
        entry = {
            "username": username,
            "alias": alias or "",
            "remark": remark or "",
            "nickname": nickname or "",
            "local_type": local_type,
        }
        contacts.append(entry)
        if username.endswith("@chatroom") and (nickname or remark):
            rooms[username] = remark or nickname

    payload = {"contacts": contacts, "rooms": rooms}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "output": str(output.resolve()),
        "contacts": len(contacts),
        "named_rooms": len(rooms),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
