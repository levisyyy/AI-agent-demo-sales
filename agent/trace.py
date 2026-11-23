# -*- coding: utf-8 -*-
"""第7层 留痕：每条 AI 消息都要能回答"当时喂了什么、为什么这么判" """
import json
import os
from datetime import datetime

LOG_PATH = os.getenv("TRACE_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trace.jsonl")


def log(record: dict) -> dict:
    record = dict(record)
    record["ts"] = datetime.now().isoformat(timespec="seconds")
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return record


def tail(n: int = 20):
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        lines = f.readlines()[-n:]
    return [json.loads(x) for x in lines if x.strip()]
