# -*- coding: utf-8 -*-
"""第7层 留痕：每条 AI 消息都要能回答"当时喂了什么、为什么这么判"。

双写：JSONL 保留文件形态（直接打开就能看，eval 用独立路径隔离），
SQLite trace_log 是分析主入口（可 SQL 聚合查询）。
"""
import json
import os
from datetime import datetime

from . import db

LOG_PATH = os.getenv("TRACE_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trace.jsonl")


def log(record: dict) -> dict:
    record = dict(record)
    record["ts"] = datetime.now().isoformat(timespec="seconds")
    source = os.getenv("TRACE_SOURCE", "demo")
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    try:
        db.log_trace(record, source=source)
    except Exception:
        pass
    return record


def tail(n: int = 20, source: str = None):
    """从 DB 读最近 n 条（时间正序）。"""
    try:
        return db.tail_trace(n, source=source)
    except Exception:
        return []
