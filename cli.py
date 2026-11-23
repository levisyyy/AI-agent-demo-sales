# -*- coding: utf-8 -*-
"""命令行演示：一条命令跑完 11 个场景，直接看决策过程。

用法：
  python3 cli.py          # 跑全部演示
  python3 cli.py -i       # 交互模式
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import Event, LLM, run, get_student

# demo 固定到 19:30 发送，避免被"静默时段"规则全拦（真实环境用 datetime.now()）
DEMO_NOW = datetime(2026, 11, 23, 19, 30)

MODE_LABEL = {
    "AUTO":    "✅ 自动发送",
    "CONFIRM": "🟡 出草稿，人工确认后发",
    "HUMAN":   "🔴 转人工",
    "STOP":    "⛔ 停止动作",
}


def show(ev: Event, llm: LLM):
    stu = get_student(ev.student_id)
    r = run(ev, llm, now=DEMO_NOW)

    print("─" * 66)
    print(f"【学员】{stu.name}  {stu.phone}  |  阶段 {stu.stage}  |  已触达 {stu.touch_count} 次  |  渠道 {stu.channel}")
    if ev.kind == "message":
        print(f"【学员说】{ev.text}")
    else:
        print(f"【事件】定时触发：{ev.trigger}")

    print("┌─ AI 决策面板 " + "─" * 51)
    if r.intent:
        print(f"│ 意图识别：{r.intent.name}   置信度 {r.intent.confidence:.2f}   情绪 {r.intent.emotion}")
    if r.plan:
        print(f"│ 策略判定：{MODE_LABEL.get(r.plan.mode, r.plan.mode)}")
        print(f"│ 决策依据：{r.plan.reason}")
        if r.plan.card_id:
            print(f"│ 话术卡片：{r.plan.card_id}   自由度 {r.plan.freedom}")
        if r.plan.tools:
            print(f"│ 调用工具：{'、'.join(r.plan.tools)}")
        if r.plan.guards:
            print(f"│ 约束提醒：{'、'.join(r.plan.guards)}")
    if r.trace.get("guard"):
        print(f"│ 风控检查：{r.trace['guard']}")
    if r.trace.get("tools"):
        print(f"│ 工具结果：{'；'.join(r.trace['tools'])}")
    print("└" + "─" * 63)

    if r.draft:
        print(f"【{'AI 草稿' if r.mode == 'CONFIRM' else '发送内容'}】{r.draft}")
    if not r.ok:
        print(f"【拦截原因】{r.blocked}")

    # 第7层真的把状态写回了，这里把它显式打出来，否则"Stage 在推进"看不见
    after = get_student(ev.student_id)
    moved = []
    if after.stage != stu.stage:
        moved.append(f"阶段 {stu.stage} → {after.stage}")
    if after.touch_count != stu.touch_count:
        moved.append(f"触达 {stu.touch_count} → {after.touch_count}")
    if moved:
        print("【状态回写】" + "　｜　".join(moved))
    print()


CASES = [
    Event("timer", "S001", trigger="class_reminder"),
    Event("message", "S002", "今天加班去不了了"),
    Event("message", "S002", "感觉有点贵啊"),
    Event("message", "S003", "你们这个老师是哪个学校的"),
    Event("message", "S004", "我想再和我家里人商量一下"),
    Event("message", "S004", "这个多少钱"),
    Event("message", "S004", "进阶班怎么报名"),
    Event("message", "S005", "太贵了，我要退费"),
    Event("message", "S005", "尾款什么时候交"),
    Event("message", "S007", "嗯嗯好的"),
    Event("timer", "S004", trigger="class_reminder"),
]


def demo():
    llm = LLM()
    print("=" * 66)
    print(" AI 督学 Agent · 全流程演示")
    print(f" 模型模式：{'真实模型 ' + llm.model if llm.available else 'MOCK 模式（未配置 LLM_API_KEY，用规则+模板跑通全流程）'}")
    print("=" * 66)
    print()
    for ev in CASES:
        show(ev, llm)


def interactive():
    llm = LLM()
    print("学员列表：S001~S008，输入 q 退出")
    while True:
        sid = input("\n学员ID > ").strip()
        if sid.lower() in ("q", "quit", ""):
            break
        text = input("学员说 > ").strip()
        print()
        try:
            show(Event("message", sid, text), llm)
        except KeyError:
            print("没有这个学员")


if __name__ == "__main__":
    interactive() if "-i" in sys.argv else demo()
