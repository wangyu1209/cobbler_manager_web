"""
Cobbler 连接配置管理
使用 JSON 文件持久化，支持运行时动态修改
"""

import os
import json
import threading

CONFIG_PATH = os.environ.get(
    "COBBLER_CONFIG_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "settings.json")
)

DEFAULT_CONFIG = {
    "cobbler_url": "http://192.168.1.10/cobbler_api",
    "cobbler_user": "cobbler",
    "cobbler_password": "cobbler",
}

_lock = threading.Lock()


def _ensure_dir():
    """确保配置目录存在"""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)


def load_config():
    """
    读取配置文件，不存在则返回默认值并自动创建文件
    """
    _ensure_dir()
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 补全可能缺失的字段
        for key, val in DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = val
        return data
    except (json.JSONDecodeError, IOError):
        return dict(DEFAULT_CONFIG)


def save_config(config):
    """
    保存配置到文件
    """
    _ensure_dir()
    with _lock:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)


def get_cobbler_url():
    return load_config().get("cobbler_url", "")


def get_cobbler_user():
    return load_config().get("cobbler_user", "")


def get_cobbler_password():
    return load_config().get("cobbler_password", "")

