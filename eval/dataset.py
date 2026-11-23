# -*- coding: utf-8 -*-
"""评估集加载与校验。

一条样本 = 一次输入 + 人工判定的正确答案。字段：

  id           样本编号，唯一
  student_id   学员 ID（决定 Stage，进而决定策略矩阵走哪一行）
  kind         message | timer
  text         学员原话（timer 留空）
  trigger      timer 的触发器，如 class_reminder
  gold_intent  人工判定的正确意图；null 表示"本就不该走到意图识别"（被闸门拦掉）
  gold_mode    人工判定的正确动作 AUTO|CONFIRM|HUMAN|STOP —— 这才是产品指标
  note         为什么这么标（给复核的人看，不参与计算）

校验故意做得严格：gold_intent 写错一个错别字，那份报告就全是假的。
"""
import json
import os

MODES = ("AUTO", "CONFIRM", "HUMAN", "STOP")
REQUIRED = ("id", "student_id", "kind", "gold_mode")


def _validate(c: dict, lineno: int, path: str) -> dict:
    name = os.path.basename(path)
    where = f"{name}:{lineno}"
    for k in REQUIRED:
        if k not in c:
            raise ValueError(f"{where} 缺少字段「{k}」")
    if c["kind"] not in ("message", "timer"):
        raise ValueError(f"{where} kind 只能是 message / timer")
    if c["gold_mode"] not in MODES:
        raise ValueError(f"{where} gold_mode 必须是 {MODES} 之一")
    if c["kind"] == "timer" and not c.get("trigger"):
        raise ValueError(f"{where} timer 事件必须给 trigger")

    gi = c.get("gold_intent")
    if gi is not None:
        from agent.router import INTENTS
        if gi not in INTENTS:
            raise ValueError(f"{where} gold_intent「{gi}」不在 router.INTENTS 里，检查拼写")

    c.setdefault("text", "")
    c.setdefault("trigger", "")
    c.setdefault("note", "")
    return c


def load_cases(path: str) -> list:
    cases, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{os.path.basename(path)}:{lineno} 不是合法 JSON（{e}）")
            c = _validate(c, lineno, path)
            if c["id"] in seen:
                raise ValueError(f"样本编号重复：{c['id']}")
            seen.add(c["id"])
            cases.append(c)

    if not cases:
        raise ValueError(f"{path} 里没有任何样本")
    return cases
