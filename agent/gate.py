# -*- coding: utf-8 -*-
"""第1层 闸门：不进模型就挡掉的活，省钱也省风险"""
from .models import Event, Student, load

_F = load("forbidden.json")
HIGH_RISK_WORDS = ["退费", "退款", "投诉", "骗子", "举报", "12315", "律师", "起诉", "曝光"]


def gate(event: Event, student: Student):
    """返回 (是否放行, 拦截原因)"""
    # 1. 触达上限：打扰学员是流失的第一原因
    if event.kind == "timer" and student.touch_count >= _F["max_touch_per_day"]:
        return False, f"触达超限（今日已 {student.touch_count} 次，上限 {_F['max_touch_per_day']}）"

    # 2. 学员消息里出现高危词，直接不走模型
    if event.kind == "message":
        for w in HIGH_RISK_WORDS:
            if w in event.text:
                return False, f"高危词命中：{w}"

    # 3. 已成交/流失的学员不再触达
    if student.stage in ("DONE", "LOST"):
        return False, "已归档，不再触达"

    return True, ""
