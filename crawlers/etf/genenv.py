# 依 ENV 讀 local.ini，寫出 .env。密碼放在 local.ini，不要提交。
import os
from configparser import ConfigParser
from pathlib import Path

ini_path = Path(__file__).resolve().parent / "local.ini"
local_config = ConfigParser()
local_config.read(ini_path, encoding="utf-8")

env_name = os.environ.get("ENV", "DEFAULT")
if env_name not in local_config:
    raise SystemExit(f"local.ini 沒有區段 {env_name}")

section = local_config[env_name]
lines = [f"{key.upper()}={section[key]}" for key in section]
env_path = Path(__file__).resolve().parent / ".env"
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"已寫入 {env_path}（區段 {env_name}）")
