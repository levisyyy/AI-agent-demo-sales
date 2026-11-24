# -*- coding: utf-8 -*-
"""第5层 执行：要事实走检索、要动作走工具、要说话才走生成"""
import re
from . import db
from .models import Student, Plan, LLM


# ---- mock 工具：上线时这一层换成真实业务系统接口，其他层不动 ----
def tool_change_schedule(stage: str) -> dict:
    return {"tool": "change_schedule", "result": "已改约至明晚 19:30", "ok": True}


def tool_add_tag(student: Student) -> dict:
    return {"tool": "add_tag", "result": f"已打标签：{student.stage}-已触达", "ok": True}


TOOLS = {"改约": tool_change_schedule, "打标签": tool_add_tag}


def retrieve(intent_name: str, kb: dict) -> str:
    """事实类问题只从知识库取，禁止模型凭记忆生成"""
    if intent_name in ("课程咨询", "到课提醒"):
        c = kb["course"]
        lines = [
            f"课程：{c['name']}，{c['duration_days']}天，每晚{c['time']}，"
            f"单次{c['daily_duration']}，{c['form']}"
        ]
        lines.append("每日主题：" + "；".join(f"{k} {v}" for k, v in c["topics"].items()))
        lines.append(f"师资：{kb['teacher']['main']}")
        return "\n".join(lines)
    if intent_name == "价格咨询":
        return "价格：以顾问一对一沟通为准，不允许自动报价。"
    return ""


def fill(card: dict, student: Student, kb: dict) -> str:
    vals = {
        "name": student.name,
        "time": kb["course"]["time"],
        "topic": kb["course"]["topics"].get(student.stage, kb["course"]["topics"]["D1"]),
        "duration": kb["course"]["daily_duration"],
        "link": "https://example.com/live/" + student.id,
        "next_time": kb["course"]["next_time"],
        "deadline": "今天 24:00",
    }
    out = card["skeleton"]
    for v in card.get("vars", []):
        out = out.replace("{" + v + "}", str(vals.get(v, "")))
    return out


SYS_GEN = """你是教育机构的私域运营助手，帮销售写发给学员的消息。
必须遵守：
1. 只做这一条消息的事，不要扩散话题；本条目标：{goal}
2. 不知道的信息绝不编造，尤其价格、政策、师资
3. 不使用绝对化用语、不承诺效果、不诱导贷款
4. 口语化，像真人微信聊天，不超过 80 字，不用 markdown
5. 只输出消息正文，不要任何解释"""


def card_by_id(card_id: str, cards: dict):
    if not card_id:
        return None
    for c in cards.values():
        if isinstance(c, dict) and c.get("card_id") == card_id:
            return c
    return None


def pick_card(plan: Plan, student: Student, intent, cards: dict):
    """卡片查找优先级：策略指定的卡片 > Stage×意图×情绪 > Stage×意图 > 通用 > 无"""
    return (card_by_id(plan.card_id, cards)
            or cards.get(f"{student.stage}|{intent.name}|{intent.emotion}")
            or cards.get(f"{student.stage}|{intent.name}|中性")
            or cards.get(f"ANY|{intent.name}|中性"))


def execute(plan: Plan, student: Student, intent, llm: LLM):
    """返回 (消息文本, 是否找到卡片)。卡片与知识库每次现读 DB，编辑即生效。"""
    cards = db.load_cards()
    kb = db.load_knowledge()

    card = pick_card(plan, student, intent, cards)
    if card is None:
        return "", False

    freedom = plan.freedom or card.get("freedom", "low")

    # 低自由度：模板+变量，完全不经过模型
    if freedom == "low" or not llm.available:
        return fill(card, student, kb), True

    # 中/高自由度：骨架做约束，模型只做润色
    facts = retrieve(intent.name, kb)
    ctx = (f"学员：{student.name}｜阶段：{student.stage}｜已上课程：{student.attended or '无'}\n"
           f"识别到的意图：{intent.name}（情绪：{intent.emotion}）\n"
           f"参考话术骨架：{fill(card, student, kb)}\n"
           f"可引用事实（只能用这些，不得新增）：{facts or '无'}")
    out = llm.chat(SYS_GEN.format(goal=card.get("goal", "")), ctx,
                   temperature=0.7 if freedom == "high" else 0.4)
    return (out.strip() if out else fill(card, student, kb)), True


def run_tools(plan: Plan, student: Student):
    done = []
    for name, fn in TOOLS.items():
        if name in plan.tools:
            done.append(fn(student.stage) if name == "改约" else fn(student))
    return done
