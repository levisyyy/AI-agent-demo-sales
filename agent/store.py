# -*- coding: utf-8 -*-
"""学员状态的进程内持有者。

demo 阶段用内存 dict 就够：既能让 Stage 推进、触达计数被真实观察到，
又不用引入数据库。接生产时把 _STATE 换成 MySQL / Redis 即可，
上层 pipeline 的调用方式不用变。

约定：get() 永远返回副本，调用方随便改也不会污染状态；
改完必须显式 commit() 才算落库——这和真实存储的语义一致。
"""
import copy

from .models import Student, load

_SEED = load("students.json")
_STATE = copy.deepcopy(_SEED)


def get(sid: str) -> Student:
    if sid not in _STATE:
        raise KeyError(sid)
    return Student(**copy.deepcopy(_STATE[sid]))


def snapshot(sid: str) -> dict:
    """给 UI / 留痕用，返回原始 dict，只读。"""
    return copy.deepcopy(_STATE[sid])


def commit(sid: str, **changes):
    if sid not in _STATE:
        raise KeyError(sid)
    _STATE[sid].update(changes)


def reset(sid: str = None):
    """回到初始快照。UI 的「清空本会话」和演示重跑都靠它。"""
    global _STATE
    if sid is None:
        _STATE = copy.deepcopy(_SEED)
    elif sid in _SEED:
        _STATE[sid] = copy.deepcopy(_SEED[sid])
    else:
        raise KeyError(sid)
