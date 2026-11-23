# -*- coding: utf-8 -*-
"""三栏工作台 UI（Streamlit）

运行：streamlit run app.py
"""
import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import Event, LLM, run, get_student      # noqa: E402
from agent import trace as trace_mod                # noqa: E402
from agent.models import load                       # noqa: E402

st.set_page_config(page_title="AI 督学 Agent", page_icon="🎯", layout="wide")

DEMO_NOW = datetime(2026, 11, 23, 19, 30)   # 演示用固定时刻，避免静默时段规则全拦
SIDS = [f"S00{i}" for i in range(1, 9)]

MODE_LABEL = {
    "AUTO": "✅ 自动发送",
    "CONFIRM": "🟡 人工确认后发",
    "HUMAN": "🔴 转人工",
    "STOP": "⛔ 停止动作",
}


@st.cache_resource
def get_llm():
    return LLM()


if "chat" not in st.session_state:
    st.session_state.chat = {s: [] for s in SIDS}
if "last" not in st.session_state:
    st.session_state.last = {}
if "sel" not in st.session_state:
    st.session_state.sel = "S001"


def push(sid, role, text):
    st.session_state.chat[sid].append({"role": role, "text": text})


def handle(ev: Event):
    stu = get_student(ev.student_id)
    r = run(ev, get_llm(), now=DEMO_NOW)
    if ev.kind == "message":
        push(ev.student_id, "student", ev.text)
    else:
        push(ev.student_id, "system", f"〔定时事件〕{ev.trigger}")

    if r.ok:
        tag = "ai_auto" if r.mode == "AUTO" else "ai_draft"
        label = "AI 已发送" if r.mode == "AUTO" else "AI 草稿 · 待确认"
        push(ev.student_id, tag, f"[{label}] {r.draft}")
    else:
        push(ev.student_id, "human", f"[已转人工] {r.blocked}")
    st.session_state.last[ev.student_id] = r


st.title("🎯 AI 督学 Agent · 运营工作台")
llm = get_llm()
st.caption(
    f"模型：{'真实模型 ' + llm.model if llm.available else 'MOCK 模式（未配置 LLM_API_KEY：用规则+模板跑通全流程）'}"
    f"　｜　演示时刻固定为 {DEMO_NOW:%m-%d %H:%M}"
)

tab_work, tab_eval = st.tabs(["工作台", "评估看板"])

# ==================== 工作台 ====================
with tab_work:
    left, mid, right = st.columns([1.0, 2.0, 1.7], gap="medium")

    with left:
        st.markdown("**学员列表**")
        for sid in SIDS:
            s = get_student(sid)
            flag = "🟡" if s.stage in ("D3", "D4") else ("🔵" if s.stage in ("D1", "D2") else "🟣")
            if st.button(f"{flag} {s.name}　{s.stage}　触达{s.touch_count}", key=f"sel_{sid}",
                         width='stretch'):
                st.session_state.sel = sid
                st.rerun()
        st.divider()
        if st.button("▶ 一键跑全部演示场景", width='stretch', type="primary"):
            demo_cases = [
                Event("timer", "S001", trigger="class_reminder"),
                Event("message", "S002", "今天加班去不了了"),
                Event("message", "S002", "感觉有点贵啊"),
                Event("message", "S003", "你们这个老师是哪个学校的"),
                Event("message", "S004", "我想再和我家里人商量一下"),
                Event("message", "S004", "这个多少钱"),
                Event("message", "S005", "太贵了，我要退费"),
                Event("message", "S007", "嗯嗯好的"),
            ]
            for ev in demo_cases:
                handle(ev)
            st.rerun()

    sid = st.session_state.sel
    stu = get_student(sid)
    r = st.session_state.last.get(sid)

    with mid:
        st.markdown(f"**{stu.name}**　`{stu.phone}`　{stu.stage}　{stu.channel}")
        st.caption(f"已上课程：{stu.attended or '无'}　｜　标签：{stu.tags}　｜　顾虑：{stu.concerns or '无'}")
        st.divider()

        box = st.container(height=430)
        for m in st.session_state.chat[sid]:
            role = m["role"]
            if role == "student":
                box.markdown(f"🙋 **学员**：{m['text']}")
            elif role == "system":
                box.markdown(f"⏱ {m['text']}")
            elif role == "ai_auto":
                box.markdown(f"🤖 {m['text']}")
            elif role == "ai_draft":
                box.warning(f"📝 {m['text']}")
            else:
                box.error(f"👤 {m['text']}")

        st.divider()
        txt = st.text_input("模拟学员发言", key=f"in_{sid}", placeholder="例：今天加班去不了了")
        c1, c2, c3 = st.columns(3)
        if c1.button("学员发送", width='stretch') and txt.strip():
            handle(Event("message", sid, txt.strip()))
            st.rerun()
        if c2.button("定时：到课提醒", width='stretch'):
            handle(Event("timer", sid, trigger="class_reminder"))
            st.rerun()
        if c3.button("清空本会话", width='stretch'):
            st.session_state.chat[sid] = []
            st.session_state.last.pop(sid, None)
            st.rerun()

    with right:
        st.markdown("**AI 决策面板**")
        if not r:
            st.info("左侧选择学员，发一条消息试试。")
        else:
            st.markdown(f"**策略判定**：{MODE_LABEL.get(r.mode, r.mode)}")
            if r.blocked:
                st.error(f"拦截：{r.blocked}")
            if r.intent:
                a, b = st.columns(2)
                a.metric("意图", r.intent.name)
                b.metric("置信度", f"{r.intent.confidence:.2f}")
                st.markdown(f"情绪：`{r.intent.emotion}`")
            if r.plan:
                st.markdown(f"决策依据：`{r.plan.reason}`")
                if r.plan.card_id:
                    st.markdown(f"话术卡片：`{r.plan.card_id}`　自由度：`{r.plan.freedom}`")
                if r.plan.tools:
                    st.markdown(f"调用工具：`{'、'.join(r.plan.tools)}`")
                if r.plan.guards:
                    st.markdown(f"约束提醒：`{'、'.join(r.plan.guards)}`")
            if r.trace.get("guard"):
                st.markdown(f"风控检查：**{r.trace['guard']}**")
            if r.trace.get("tools"):
                st.success("；".join(r.trace["tools"]))
            with st.expander("完整 trace（留痕）"):
                st.json(r.trace)

# ==================== 评估看板 ====================
with tab_eval:
    st.markdown("**历史运行留痕**（每次决策都会写入 `trace.jsonl`，可回溯当时喂了什么上下文）")
    rows = trace_mod.tail(200)
    if not rows:
        st.info("还没有记录。先在工作台跑几条。")
    else:
        df = pd.DataFrame(rows)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("总调用", len(df))
        c2.metric("自动发送占比", f"{(df.get('mode') == 'AUTO').mean() * 100:.0f}%"
                  if "mode" in df else "-")
        c3.metric("转人工占比", f"{(df.get('mode') == 'HUMAN').mean() * 100:.0f}%"
                  if "mode" in df else "-")
        blocked = df["blocked"].notna().sum() if "blocked" in df else 0
        c4.metric("被拦截次数", int(blocked))
        show_cols = [c for c in ["ts", "student", "stage", "intent", "confidence",
                                 "mode", "card", "freedom", "guard", "blocked"] if c in df.columns]
        st.dataframe(df[show_cols], width='stretch', height=420)

    st.divider()
    st.markdown("**策略矩阵一览**（这张表就是产品定义的落地）")
    from agent.policy import MATRIX
    mrows = [{"Stage": k[0], "意图": k[1], "处理方式": v[0],
              "话术卡片": v[1] or "—", "自由度": v[2] or "—"} for k, v in MATRIX.items()]
    st.dataframe(pd.DataFrame(mrows), width='stretch', height=420)

    st.divider()
    st.markdown("**话术卡片库**")
    cards = load("cards.json")
    crow = [{"卡片ID": c.get("card_id", ""), "组合": k, "自由度": c.get("freedom", ""),
             "目标": c.get("goal", ""), "骨架": c.get("skeleton", "")}
            for k, c in cards.items() if isinstance(c, dict)]
    st.dataframe(pd.DataFrame(crow), width='stretch', height=320)
