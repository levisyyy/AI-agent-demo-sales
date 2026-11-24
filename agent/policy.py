# -*- coding: utf-8 -*-
"""第4层 策略决策 —— 整个产品的核心。

策略 = f(Stage, 意图, 情绪, 置信度, 触达次数)
注意：路由键是 (Stage, 意图) 的复合键，不是单独意图。
同一句"有点贵"，D2 和 D5 的处理完全不同。
"""
from .models import Plan, Intent, Student
from .stage import allowed_freedom
from . import db

# ---- 策略矩阵：实际项目中应配置化（放 JSON / 后台），让运营自助维护 ----
# mode: AUTO=直接发 / CONFIRM=出草稿人工确认 / HUMAN=强制转人工 / STOP=不动作
MATRIX = {
    ("D1", "到课提醒"):   ("AUTO",    "D1-01", "low",  []),
    ("D1", "师资咨询"):   ("AUTO",    "K-01",  "low",  ["检索知识库"]),
    ("D1", "课程咨询"):   ("AUTO",    "D1-02", "low",  []),
    ("D1", "价格咨询"):   ("HUMAN",   "",      "",     ["没上课就谈价，人接"]),
    ("D1", "异议嫌贵"):   ("HUMAN",   "",      "",     ["D1 谈价过早，人接"]),
    ("D1", "情绪安抚"):   ("CONFIRM", "D1-03", "high", []),
    ("D1", "临时改约"):   ("AUTO",    "D2-02", "low",  ["改约"]),
    ("D1", "犹豫"):       ("CONFIRM", "D2-04", "mid",  []),
    ("D1", "无效内容"):   ("HUMAN",   "",      "",     ["识别不了，人接"]),

    ("D2", "到课提醒"):   ("AUTO",    "D2-01", "low",  []),
    ("D2", "临时改约"):   ("AUTO",    "D2-02", "low",  ["改约"]),
    ("D2", "师资咨询"):   ("AUTO",    "K-01",  "low",  ["检索知识库"]),
    ("D2", "课程咨询"):   ("AUTO",    "D1-02", "low",  []),
    ("D2", "异议嫌贵"):   ("CONFIRM", "D2-03", "mid",  ["不报价"]),
    ("D2", "价格咨询"):   ("HUMAN",   "",      "",     ["价格不给模型生成"]),
    ("D2", "犹豫"):       ("CONFIRM", "D2-04", "mid",  []),
    ("D2", "情绪安抚"):   ("CONFIRM", "D1-03", "high", []),
    ("D2", "无效内容"):   ("HUMAN",   "",      "",     ["识别不了，人接"]),

    ("D3", "到课提醒"):   ("AUTO",    "D2-01", "low",  []),
    ("D3", "师资咨询"):   ("AUTO",    "K-01",  "low",  ["检索知识库"]),
    ("D3", "课程咨询"):   ("AUTO",    "D3-02", "low",  ["检索知识库"]),
    ("D3", "异议嫌贵"):   ("CONFIRM", "D3-03", "mid",  ["不报价"]),
    ("D3", "价格咨询"):   ("HUMAN",   "",      "",     ["D4 之前不报价，人接"]),
    ("D3", "犹豫"):       ("CONFIRM", "D2-04", "mid",  []),
    ("D3", "情绪安抚"):   ("CONFIRM", "D3-01", "high", []),
    ("D3", "临时改约"):   ("AUTO",    "D2-02", "low",  ["改约"]),
    ("D3", "无效内容"):   ("HUMAN",   "",      "",     ["识别不了，人接"]),

    ("D4", "转化铺垫"):   ("CONFIRM", "D4-01", "low",  ["报价", "发支付链接"]),
    ("D4", "犹豫"):       ("CONFIRM", "D4-02", "mid",  []),
    ("D4", "到课提醒"):   ("AUTO",    "",      "low",  []),
    ("D4", "异议嫌贵"):   ("HUMAN",   "",      "",     ["成交期，价格必须人接"]),
    ("D4", "价格咨询"):   ("HUMAN",   "",      "",     ["价格必须人接"]),
    ("D4", "师资咨询"):   ("AUTO",    "K-01",  "low",  ["检索知识库"]),
    ("D4", "课程咨询"):   ("CONFIRM", "D3-02", "mid",  []),
    ("D4", "情绪安抚"):   ("HUMAN",   "",      "",     ["成交期情绪，人接"]),
    ("D4", "临时改约"):   ("AUTO",    "D2-02", "low",  ["改约"]),
    ("D4", "无效内容"):   ("HUMAN",   "",      "",     ["识别不了，人接"]),

    ("D5", "尾款提醒"):   ("CONFIRM", "D5-01", "low",  ["报价", "催收"]),
    ("D5", "到课提醒"):   ("AUTO",    "",      "low",  []),
    ("D5", "异议嫌贵"):   ("HUMAN",   "",      "",     ["涉及退款风险，人接"]),
    ("D5", "价格咨询"):   ("HUMAN",   "",      "",     ["价格必须人接"]),
    ("D5", "犹豫"):       ("HUMAN",   "",      "",     ["成交末段，人接"]),
    ("D5", "情绪安抚"):   ("HUMAN",   "",      "",     ["成交末段，人接"]),
    ("D5", "师资咨询"):   ("AUTO",    "K-01",  "low",  ["检索知识库"]),
    ("D5", "课程咨询"):   ("CONFIRM", "D3-02", "mid",  []),
    ("D5", "临时改约"):   ("HUMAN",   "",      "",     ["尾款期改约=有流失信号"]),
    ("D5", "无效内容"):   ("HUMAN",   "",      "",     ["识别不了，人接"]),
}

DEFAULT = ("HUMAN", "", "", ["策略矩阵无此组合，兜底转人工"])

# 涉及金额与情绪的意图，任何 Stage 都不给自动发送权
NEVER_AUTO = {"价格咨询", "异议嫌贵"}

# 矩阵第 5 列里，属于"真工具"的名字；其余视为约束说明
TOOL_NAMES = {"改约", "打标签"}


def decide(stage: str, intent: Intent, student: Student, is_timer: bool = False) -> Plan:
    # ① 触达频率——只对"主动推送"设限；学员自己发消息来是互动，不是打扰
    #    （gate 已在上游做同样拦截，这里保留一份，防止策略层被单独调用时绕过频控）
    #    阈值只有一处真相：DB 的 settings 表
    limit = db.get_setting("max_touch_per_day", 3)
    if is_timer and student.touch_count >= limit:
        return Plan("STOP", reason=f"今日主动触达已达上限（{limit}次），停止推送")

    # ② 置信度——模型没底就闭嘴
    if intent.confidence < 0.75:
        return Plan("HUMAN", reason=f"置信度 {intent.confidence:.2f} < 0.75，进人工队列")

    mode, card_id, freedom, extra = MATRIX.get((stage, intent.name), DEFAULT)

    # ③ 硬规则兜底：钱永远不给自动
    if intent.name in NEVER_AUTO and mode == "AUTO":
        mode = "CONFIRM"

    # ④ 负面情绪升档：情绪激动时人工接管
    if intent.emotion == "负面" and mode == "AUTO":
        mode = "CONFIRM"

    # ⑤ Stage 权限封顶：D4/D5 不允许出现高自由度
    cap = allowed_freedom(stage)
    order = {"low": 0, "mid": 1, "high": 2}
    if freedom and order.get(freedom, 0) > order.get(cap, 0):
        freedom = cap

    return Plan(mode, card_id, freedom,
                reason=f"{stage}×{intent.name} → {mode}",
                tools=[x for x in extra if x in TOOL_NAMES],
                guards=[x for x in extra if x not in TOOL_NAMES])
