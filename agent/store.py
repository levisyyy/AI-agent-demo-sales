# -*- coding: utf-8 -*-
"""学员状态：内存是工作副本，SQLite（agent/db.py）是持久层。

约定：get() 永远返回副本，调用方随便改也不会污染状态；
改完必须显式 commit()，同时写内存和 DB——和真实存储的语义一致。
reset() 从 DB 重读（丢弃内存改动）：评估框架靠它保证样本互相独立，
工作台改完数据也靠它让下一次运行拿到新值。
"""
import copy

from . import db
from .models import Student

_STATE = None


def _ensure():
    global _STATE
    if _STATE is None:
        _STATE = {s["id"]: dict(s) for s in db.load_students()}


def get(sid: str) -> Student:
    _ensure()
    if sid not in _STATE:
        raise KeyError(sid)
    return Student(**copy.deepcopy(_STATE[sid]))


def snapshot(sid: str) -> dict:
    """给 UI / 留痕用，返回原始 dict，只读。"""
    _ensure()
    return copy.deepcopy(_STATE[sid])


def commit(sid: str, **changes):
    _ensure()
    _STATE[sid].update(changes)
    db.update_student(sid, changes)


def reset(sid: str = None):
    """从 DB 重读。sid=None 全量重置（评估回放、工作台保存后都用它）。"""
    global _STATE
    _STATE = {s["id"]: dict(s) for s in db.load_students()}
