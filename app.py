# -*- coding: utf-8 -*-
"""三栏工作台 UI（Streamlit）

运行：streamlit run app.py
"""
import json
import os
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import Event, LLM, run, get_student, store, db   # noqa: E402
from agent import trace as trace_mod                # noqa: E402

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

tab_work, tab_eval, tab_data = st.tabs(["工作台", "评估看板", "数据管理"])

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
            db.reseed_students()   # 回到初始学员数据，保证每次演示可重复
            store.reset()
            demo_cases = [
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
        if c3.button("重置学员数据", width='stretch'):
            st.session_state.chat[sid] = []
            st.session_state.last.pop(sid, None)
            db.reseed_students()      # 从 students.json 回灌，触达数与 Stage 回到初始
            store.reset()
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
    cards = db.load_cards()
    crow = [{"卡片ID": c.get("card_id", ""), "组合": k, "自由度": c.get("freedom", ""),
             "目标": c.get("goal", ""), "骨架": c.get("skeleton", "")}
            for k, c in cards.items() if isinstance(c, dict)]
    st.dataframe(pd.DataFrame(crow), width='stretch', height=320)

# ==================== 数据管理 ====================
LIST_FIELDS = {"attended": "已上课程", "tags": "标签", "concerns": "顾虑"}


def _join(v):
    return ", ".join(v) if isinstance(v, list) else ("" if v is None else v)


def _split(v):
    return [x.strip() for x in str(v).split(",") if x.strip()]


def _num(v, default=None):
    try:
        return default if v is None or pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return default


with tab_data:
    st.markdown(
        "数据存在 `data/agent.db`（SQLite，单文件）。**改完点保存立即生效**，"
        "不用重启；`data/*.json` 只在首次建库时导入一次，之后以这里为准。"
        "注意：工作台的「一键演示」和「重置学员数据」会把学员恢复成 `students.json` 初始值。"
    )

    st.subheader("对话日志（trace_log，每次决策一行）")
    st.caption("怎么调的、怎么判的都在这里：意图与置信度、命中的策略与卡片、风控结论，"
               "以及每次模型调用的完整 prompt 与回复（llm_calls 字段）。分析 SQL 见 `docs/log-analysis.md`。")
    logs = db.tail_trace(100)
    if not logs:
        st.info("还没有日志，去工作台发一条消息。")
    else:
        log_df = pd.DataFrame(logs)
        show = [c for c in ["id", "ts", "source", "student", "stage", "intent", "confidence",
                            "mode", "card", "freedom", "guard", "blocked"] if c in log_df.columns]
        st.dataframe(log_df[show], width='stretch', height=300)
        sel = st.selectbox(
            "查看某条的完整明细",
            options=logs,
            format_func=lambda r: f"#{r['id']} {r['ts']} {r['student']} {r['intent']} → {r['mode']}")
        st.json(sel)
        if st.button("清空全部日志", key="clear_trace"):
            db.clear_trace()
            st.rerun()

    st.subheader("学员档案")
    stu_rows = db.load_students()
    stu_df = pd.DataFrame([
        {"id": s["id"], "name": s["name"], "phone": s["phone"], "channel": s["channel"],
         "course": s["course"], "stage": s["stage"],
         "enrolled_days": s["enrolled_days"], "touch_count": s["touch_count"],
         "已上课程": _join(s["attended"]), "标签": _join(s["tags"]),
         "顾虑": _join(s["concerns"]),
         "付订金": bool(s["paid_deposit"]), "尾款结清": bool(s["paid_final"])}
        for s in stu_rows])
    stu_edit = st.data_editor(
        stu_df, num_rows="dynamic", width='stretch',
        column_config={
            "stage": st.column_config.SelectboxColumn("Stage", options=["D1", "D2", "D3", "D4", "D5", "DONE", "LOST"]),
            "paid_deposit": st.column_config.CheckboxColumn("付订金"),
            "paid_final": st.column_config.CheckboxColumn("尾款结清"),
        }, key="stu_editor")
    if st.button("保存学员", key="save_students"):
        try:
            out = []
            for _, r in stu_edit.iterrows():
                out.append({
                    "id": str(r["id"]).strip(), "name": str(r["name"]),
                    "phone": str(r["phone"]), "channel": str(r["channel"]),
                    "course": str(r["course"]), "stage": str(r["stage"]),
                    "enrolled_days": int(_num(r["enrolled_days"], 0) or 0),
                    "touch_count": int(_num(r["touch_count"], 0) or 0),
                    "last_reply_hours": _num(r["last_reply_hours"]),
                    "attended": _split(r["已上课程"]), "tags": _split(r["标签"]),
                    "concerns": _split(r["顾虑"]),
                    "paid_deposit": bool(r["付订金"]), "paid_final": bool(r["尾款结清"]),
                })
            db.save_students(out)
            store.reset()
            st.success(f"已保存 {len(out)} 条学员，工作台下一次运行即生效")
        except Exception as e:
            st.error(f"保存失败：{e}")

    st.divider()
    st.subheader("话术卡片库")
    card_rows = [{"stage": k.split("|")[0], "intent": k.split("|")[1], "emotion": k.split("|")[2],
                  "card_id": c["card_id"], "freedom": c["freedom"], "goal": c["goal"],
                  "skeleton": c["skeleton"], "vars": _join(c["vars"])}
                 for k, c in db.load_cards().items()]
    card_df = pd.DataFrame(card_rows)
    card_edit = st.data_editor(
        card_df, num_rows="dynamic", width='stretch', height=420,
        column_config={
            "stage": st.column_config.SelectboxColumn("Stage", options=["D1", "D2", "D3", "D4", "D5", "ANY"]),
            "freedom": st.column_config.SelectboxColumn("自由度", options=["low", "mid", "high"]),
        }, key="card_editor")
    if st.button("保存卡片", key="save_cards"):
        try:
            out = []
            for _, r in card_edit.iterrows():
                out.append({
                    "stage": str(r["stage"]).strip(), "intent": str(r["intent"]).strip(),
                    "emotion": str(r["emotion"]).strip() or "中性",
                    "card_id": str(r["card_id"]).strip(),
                    "freedom": str(r["freedom"]).strip() or "low",
                    "goal": str(r["goal"]), "skeleton": str(r["skeleton"]),
                    "vars": _split(r["vars"]),
                })
            db.save_cards(out)
            st.success(f"已保存 {len(out)} 张卡片")
        except Exception as e:
            st.error(f"保存失败：{e}")

    st.divider()
    st.subheader("禁语清单（一行一个词，命中即拦截）")
    fb = db.load_forbidden()
    word_df = pd.DataFrame([{"word": w} for w in fb["hard_block"]])
    word_edit = st.data_editor(word_df, num_rows="dynamic", width='stretch', height=300,
                               key="word_editor")
    if st.button("保存禁语", key="save_words"):
        db.save_forbidden([str(r["word"]) for _, r in word_edit.iterrows()], {})
        st.success("禁语已保存，下一条消息立即生效")

    st.divider()
    st.subheader("频控与时段")
    c1, c2, c3 = st.columns(3)
    max_touch = c1.number_input("每日主动触达上限", min_value=1, max_value=20,
                                value=int(fb["max_touch_per_day"]), key="max_touch")
    quiet_start = c2.number_input("静默开始（时）", min_value=0, max_value=23,
                                  value=int(fb["quiet_hours"]["start"]), key="quiet_start")
    quiet_end = c3.number_input("静默结束（时）", min_value=0, max_value=23,
                                value=int(fb["quiet_hours"]["end"]), key="quiet_end")
    st.caption(f"金额正则（技术项，改完要自测）：`{json.dumps(fb['price_patterns'], ensure_ascii=False)}`")
    if st.button("保存频控与时段", key="save_settings"):
        db.save_forbidden(fb["hard_block"], {
            "max_touch_per_day": int(max_touch),
            "quiet_hours": {"start": int(quiet_start), "end": int(quiet_end)},
        })
        st.success("已保存")
