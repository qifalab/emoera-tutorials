"""资源分类管理：管理员可维护固定的分类选项（增删）。

分类持久化到 categories.json，结构：
    {"categories": ["教程", "模型", "资料"]}

上传资源时前端从这些固定项中选择；分类在生产/展示中作为普通字符串，
管理员删除某个分类不影响已有资源的 category 字段（仅影响下次可选项）。
"""

import json
import os
import threading

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
FILE = os.path.join(DATA_DIR, "categories.json")

# 默认分类（首次运行或文件缺失时）
DEFAULT_CATEGORIES = ["教程", "模型", "资料", "工具", "数据集"]

_LOCK = threading.Lock()


def _load() -> list:
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("categories", DEFAULT_CATEGORIES)
    except Exception:  # noqa: BLE001
        return list(DEFAULT_CATEGORIES)


def _save(categories: list) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"categories": categories}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, FILE)


def list_categories() -> list:
    """返回固定分类列表。"""
    with _LOCK:
        return _load()


def add_category(name: str) -> tuple[bool, str]:
    """新增一个分类。返回 (ok, msg)。"""
    name = (name or "").strip()
    if not name:
        return False, "分类名不能为空"
    if len(name) > 40:
        return False, "分类名过长（≤40 字）"
    with _LOCK:
        cats = _load()
        if name in cats:
            return False, "分类已存在"
        cats.append(name)
        _save(cats)
    return True, "已添加"


def remove_category(name: str) -> tuple[bool, str]:
    """删除一个分类。返回 (ok, msg)。"""
    name = (name or "").strip()
    with _LOCK:
        cats = _load()
        if name not in cats:
            return False, "分类不存在"
        if len(cats) <= 1:
            return False, "至少保留一个分类"
        cats = [c for c in cats if c != name]
        _save(cats)
    return True, "已删除"


def valid_name(name: str) -> bool:
    """校验分类名是否在当前固定清单内（上传时兜底）。"""
    return (name or "").strip() in list_categories()
