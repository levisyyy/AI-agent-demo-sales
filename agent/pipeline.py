# -*- coding: utf-8 -*-
"""主流程：七层串成一条线。这个函数结构本身就是产品设计。"""
from .models import Event, Student, Result, LLM
from .gate import gate
from .router import classify, classify_event
from .policy import decide
from .executor import execute, run_tools
from .guard import check
from .stage import advance, goal_of
from . import store
from . import trace as trace_mod


def get_student(sid: str) -> Student:
    return store.get(sid)


def run(event: Event, llm: LLM = None, now=None) -> Result:
    llm = llm or LLM()
    student = get_student(event.student_id)
    t = {"student": student.name, "stage": student.stage, "event": event.kind}

    # ── 第1层 闸门 ──
    ok, why = gate(event, student)
    if not ok:
        return Result(False, "HUMAN", blocked=why, trace=trace_mod.log({**t, "blocked": why}))

    # ── 第3层 意图识别（定时事件不消耗模型）──
    intent = classify_event(event.trigger) if event.kind == "timer" else classify(event.text, llm)
    t["intent"] = intent.name
    t["confidence"] = round(intent.confidence, 2)

    # ── 第4层 策略决策 ──
    plan = decide(student.stage, intent, student, is_timer=(event.kind == "timer"))
    t.update({"mode": plan.mode, "card": plan.card_id, "freedom": plan.freedom, "reason": plan.reason})

    if plan.mode in ("HUMAN", "STOP"):
        # blocked 也要落盘，否则评估看板的"被拦截次数"漏掉策略层转人工
        return Result(False, plan.mode, intent=intent, plan=plan,
                      blocked=plan.reason, trace=trace_mod.log({**t, "blocked": plan.reason}))

    # ── 第5层 执行 ──
    draft, found = execute(plan, student, intent, llm)
    if not found:
        # 没有对应话术卡片 = 这个场景没定义过，不许即兴发挥
        t["blocked"] = "无匹配话术卡片"
        return Result(False, "HUMAN", intent=intent, plan=plan,
                      blocked="无匹配话术卡片，转人工", trace=trace_mod.log(t))
    t["draft"] = draft

    # ── 第6层 风控闸门 ──
    passed, why, force_confirm = check(draft, student.stage, now=now,
                                       is_reply=(event.kind == "message"))
    if not passed:
        t["guard"] = f"拦截：{why}"
        return Result(False, "HUMAN", draft=draft, intent=intent, plan=plan,
                      blocked=why, trace=trace_mod.log(t))

    if force_confirm and plan.mode == "AUTO":
        plan.mode = "CONFIRM"
        plan.reason += "｜静默时段，主动推送降级为草稿"
        t["mode"] = plan.mode
    t["guard"] = "通过（静默时段，降级为草稿）" if force_confirm else "通过"

    # ── 第7层 工具 + 状态回写 + 留痕 ──
    tools = run_tools(plan, student)
    t["tools"] = [x["result"] for x in tools]

    next_stage = advance(student.stage, student.attended, student.paid_final)
    changes = {}
    if next_stage != student.stage:
        changes["stage"] = next_stage
        t["next_stage"] = next_stage
    # 只有主动推送才计入"打扰次数"；学员自己开口是互动，不该消耗频控额度
    if event.kind == "timer":
        changes["touch_count"] = student.touch_count + 1
    else:
        changes["last_reply_hours"] = 0
    t["touch_count"] = changes.get("touch_count", student.touch_count)
    t["next_goal"] = goal_of(next_stage)
    store.commit(student.id, **changes)

    trace_mod.log(t)
    return Result(True, plan.mode, draft=draft, intent=intent, plan=plan, trace=t)
