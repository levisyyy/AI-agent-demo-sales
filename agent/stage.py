# -*- coding: utf-8 -*-
"""Stage 状态机 —— Agent 推的从来不是"回复"，是 Stage 迁移"""

STAGES = {
    "D1": {"index": 0, "goal": "进第1天直播间",        "win": "实际到课",        "ai_level": "high"},
    "D2": {"index": 1, "goal": "上完第2课并产生正反馈",  "win": "到课+有互动",     "ai_level": "high"},
    "D3": {"index": 2, "goal": "建信任、摸清意向与顾虑", "win": "意向标签被打上",   "ai_level": "mid"},
    "D4": {"index": 3, "goal": "推动付订金",           "win": "订金支付成功",     "ai_level": "low"},
    "D5": {"index": 4, "goal": "补齐尾款",             "win": "尾款支付成功",     "ai_level": "min"},
    "DONE": {"index": 5, "goal": "归因复盘",           "win": "标签归档",         "ai_level": "none"},
}

# 每个 Stage 允许 AI 的最高自由度，用于 policy 层兜底
FREEDOM_CAP = {"high": "high", "mid": "mid", "low": "low", "min": "low", "none": "low"}


def advance(stage: str, attended: list, paid_final: bool) -> str:
    """根据实际行为推进 Stage —— 不是靠对话说的，是靠行为事实

    D5 的 win 是"尾款支付成功"，所以归档看 paid_final。
    只看订金会把"还在问尾款什么时候交"的学员误判成已完成。
    """
    if stage == "D5" and paid_final and len(attended) >= 4:
        return "DONE"
    return stage


def allowed_freedom(stage: str) -> str:
    return FREEDOM_CAP.get(STAGES.get(stage, {}).get("ai_level", "low"), "low")


def goal_of(stage: str) -> str:
    return STAGES.get(stage, {}).get("goal", "")
