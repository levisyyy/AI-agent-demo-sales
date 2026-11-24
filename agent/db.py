# -*- coding: utf-8 -*-
"""SQLite 数据层：data/agent.db 单文件，标准库 sqlite3，零安装。

设计决定：
- JSON 文件保留，但只在**首次建库**时作为 seed 导入一次；之后以 DB 为唯一真相，
  避免"两处数据各改各的"。想从 JSON 重灌，调 reseed()。
- 四张表对应四个 JSON，但 cards 的复合键拆成了 stage/intent/emotion 三列，
  knowledge 的嵌套 dict 拍平成 (section, k, v) 行——为的是表格可视化编辑。
- load_* 返回的结构与原 JSON **完全同构**，上层模块（gate/guard/executor）不用改逻辑。
- 生产换 MySQL/Postgres 时，只替换这个文件的实现，接口不变。
"""
import json
import os
import sqlite3

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "agent.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
  id TEXT PRIMARY KEY, name TEXT, phone TEXT, channel TEXT, course TEXT, stage TEXT,
  enrolled_days INTEGER DEFAULT 0, attended TEXT DEFAULT '[]', touch_count INTEGER DEFAULT 0,
  last_reply_hours REAL, tags TEXT DEFAULT '[]', concerns TEXT DEFAULT '[]',
  paid_deposit INTEGER DEFAULT 0, paid_final INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stage TEXT, intent TEXT, emotion TEXT, card_id TEXT UNIQUE,
  freedom TEXT, goal TEXT, skeleton TEXT, vars TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS knowledge (
  section TEXT, k TEXT, v TEXT, PRIMARY KEY (section, k)
);
CREATE TABLE IF NOT EXISTS forbidden_words (
  word TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS trace_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, source TEXT DEFAULT 'demo',
  student_id TEXT, student TEXT, stage TEXT, event TEXT,
  intent TEXT, confidence REAL, mode TEXT, card TEXT, freedom TEXT,
  reason TEXT, draft TEXT, guard TEXT, blocked TEXT,
  touch_count INTEGER, next_stage TEXT, next_goal TEXT,
  llm_calls TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_trace_ts ON trace_log(ts);
CREATE INDEX IF NOT EXISTS idx_trace_student ON trace_log(student_id);
"""

_initialized = False


def _conn():
    return sqlite3.connect(DB_PATH)


def _json_load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def _seed_students_only():
    conn = _conn()
    try:
        conn.execute("DELETE FROM students")
        for sid, s in _json_load("students.json").items():
            conn.execute(
                "INSERT OR REPLACE INTO students VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s["id"], s["name"], s["phone"], s["channel"], s["course"], s["stage"],
                 s["enrolled_days"], json.dumps(s["attended"], ensure_ascii=False),
                 s["touch_count"], s["last_reply_hours"],
                 json.dumps(s["tags"], ensure_ascii=False),
                 json.dumps(s["concerns"], ensure_ascii=False),
                 int(s["paid_deposit"]), int(s.get("paid_final", 0))))
        conn.commit()
    finally:
        conn.close()


def _seed():
    """从 4 个 JSON 首次导入。JSON 之后只读，不再同步。"""
    _seed_students_only()
    conn = _conn()
    try:
        # cards：复合键 "D1|到课提醒|中性" 拆成三列
        for key, c in _json_load("cards.json").items():
            if key.startswith("_"):
                continue
            stage, intent, emotion = key.split("|")
            conn.execute(
                "INSERT OR IGNORE INTO cards (stage,intent,emotion,card_id,freedom,goal,skeleton,vars)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (stage, intent, emotion, c["card_id"], c["freedom"], c["goal"],
                 c["skeleton"], json.dumps(c.get("vars", []), ensure_ascii=False)))
        # knowledge：嵌套拍平成行，topics 的子键记作 topics_D1 这种格式
        kb = _json_load("knowledge.json")
        flat = {}
        for section, d in kb.items():
            if section.startswith("_"):
                continue
            for k, v in d.items():
                if isinstance(v, dict):
                    for sk, sv in v.items():
                        flat[(section, f"{k}_{sk}")] = str(sv)
                else:
                    flat[(section, k)] = str(v)
        conn.executemany("INSERT OR REPLACE INTO knowledge VALUES (?,?,?)",
                         [(s, k, v) for (s, k), v in flat.items()])
        # forbidden
        fb = _json_load("forbidden.json")
        conn.executemany("INSERT OR IGNORE INTO forbidden_words VALUES (?)",
                         [(w,) for w in fb["hard_block"]])
        conn.executemany("INSERT OR REPLACE INTO settings VALUES (?,?)", [
            ("price_patterns", json.dumps(fb["price_patterns"], ensure_ascii=False)),
            ("quiet_hours", json.dumps(fb["quiet_hours"], ensure_ascii=False)),
            ("max_touch_per_day", str(fb["max_touch_per_day"])),
        ])
        conn.commit()
    finally:
        conn.close()


def _init():
    global _initialized
    if _initialized:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = _conn()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    if not os.path.exists(os.path.join(DATA_DIR, ".seeded")):
        _seed()
        open(os.path.join(DATA_DIR, ".seeded"), "w").close()
    _initialized = True


def reseed_students():
    """只重灌学员表（从 students.json）。演示和评估用：跑之前回到初始状态。

    注意会覆盖你在工作台里对学员的手工编辑；卡片/禁语/知识库不受影响。
    """
    _init()
    _seed_students_only()


def reseed():
    """从 JSON 重灌全部数据（慎用：会覆盖 DB 里的手工编辑）。"""
    conn = _conn()
    try:
        for t in ("students", "cards", "knowledge", "forbidden_words", "settings"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.close()
    _seed()


# ---------------- students ----------------

def load_students() -> list:
    _init()
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM students ORDER BY id").fetchall()
        cols = [c[0] for c in conn.execute("SELECT * FROM students LIMIT 1").description]
    finally:
        conn.close()
    out = []
    for row in rows:
        d = dict(zip(cols, row))
        d["attended"] = json.loads(d["attended"])
        d["tags"] = json.loads(d["tags"])
        d["concerns"] = json.loads(d["concerns"])
        d["paid_deposit"] = bool(d["paid_deposit"])
        d["paid_final"] = bool(d["paid_final"])
        out.append(d)
    return out


def update_student(sid: str, changes: dict):
    _init()
    conn = _conn()
    try:
        for k, v in changes.items():
            if k in ("attended", "tags", "concerns"):
                v = json.dumps(v, ensure_ascii=False)
            elif k in ("paid_deposit", "paid_final"):
                v = int(v)
            conn.execute(f"UPDATE students SET {k}=? WHERE id=?", (v, sid))
        conn.commit()
    finally:
        conn.close()


def save_students(rows: list):
    """整表覆盖（表格编辑用）。rows 的数组字段需已是 list，bool 字段已是 bool。"""
    _init()
    conn = _conn()
    try:
        conn.execute("DELETE FROM students")
        for s in rows:
            conn.execute(
                "INSERT OR REPLACE INTO students VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s["id"], s["name"], s["phone"], s["channel"], s["course"], s["stage"],
                 int(s.get("enrolled_days", 0)),
                 json.dumps(s.get("attended", []), ensure_ascii=False),
                 int(s.get("touch_count", 0)),
                 s.get("last_reply_hours"),
                 json.dumps(s.get("tags", []), ensure_ascii=False),
                 json.dumps(s.get("concerns", []), ensure_ascii=False),
                 int(bool(s.get("paid_deposit", False))),
                 int(bool(s.get("paid_final", False)))))
        conn.commit()
    finally:
        conn.close()


# ---------------- cards ----------------

def load_cards() -> dict:
    """返回与原 cards.json 同构的 {\"D1|到课提醒|中性\": {...}}。"""
    _init()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT stage,intent,emotion,card_id,freedom,goal,skeleton,vars FROM cards"
        ).fetchall()
    finally:
        conn.close()
    out = {}
    for stage, intent, emotion, cid, freedom, goal, skeleton, vars_json in rows:
        out[f"{stage}|{intent}|{emotion}"] = {
            "card_id": cid, "freedom": freedom, "goal": goal,
            "skeleton": skeleton, "vars": json.loads(vars_json),
        }
    return out


def save_cards(rows: list):
    """整表覆盖。rows 每条含 stage/intent/emotion/card_id/freedom/goal/skeleton/vars(list)。"""
    _init()
    conn = _conn()
    try:
        conn.execute("DELETE FROM cards")
        for c in rows:
            conn.execute(
                "INSERT INTO cards (stage,intent,emotion,card_id,freedom,goal,skeleton,vars)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (c["stage"], c["intent"], c["emotion"], c["card_id"], c["freedom"],
                 c["goal"], c["skeleton"], json.dumps(c.get("vars", []), ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()


# ---------------- knowledge ----------------

def load_knowledge() -> dict:
    """重建出与原 knowledge.json 同构的嵌套 dict。"""
    _init()
    conn = _conn()
    try:
        rows = conn.execute("SELECT section,k,v FROM knowledge").fetchall()
    finally:
        conn.close()
    out = {}
    for section, k, v in rows:
        node = out.setdefault(section, {})
        if k.startswith("topics_"):
            node.setdefault("topics", {})[k[len("topics_"):]] = _smart(v)
        else:
            node[k] = _smart(v)
    return out


def _smart(v: str):
    """数字-looking 的字符串还原成数字，其余保持字符串。"""
    try:
        return int(v)
    except ValueError:
        return v


def save_knowledge(rows: list):
    _init()
    conn = _conn()
    try:
        conn.execute("DELETE FROM knowledge")
        conn.executemany("INSERT OR REPLACE INTO knowledge VALUES (?,?,?)",
                         [(r["section"], r["k"], r["v"]) for r in rows])
        conn.commit()
    finally:
        conn.close()


# ---------------- forbidden / settings ----------------

def load_forbidden() -> dict:
    """与原 forbidden.json 同构（不含 _meta）。"""
    _init()
    conn = _conn()
    try:
        words = [r[0] for r in conn.execute("SELECT word FROM forbidden_words ORDER BY word")]
        settings = dict(conn.execute("SELECT key,value FROM settings").fetchall())
    finally:
        conn.close()
    return {
        "hard_block": words,
        "price_patterns": json.loads(settings["price_patterns"]),
        "quiet_hours": json.loads(settings["quiet_hours"]),
        "max_touch_per_day": int(settings["max_touch_per_day"]),
    }


def get_setting(key: str, default=None):
    _init()
    conn = _conn()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return default
    return _smart(row[0])


def save_forbidden(words: list, settings: dict):
    _init()
    conn = _conn()
    try:
        conn.execute("DELETE FROM forbidden_words")
        conn.executemany("INSERT OR IGNORE INTO forbidden_words VALUES (?)",
                         [(w.strip(),) for w in words if w.strip()])
        for k, v in settings.items():
            value = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (k, value))
        conn.commit()
    finally:
        conn.close()


# ---------------- trace 日志（每次决策一行，分析的主入口） ----------------

def log_trace(record: dict, source: str = "demo"):
    _init()
    llm_calls = record.get("llm_calls") or []
    if not isinstance(llm_calls, str):
        llm_calls = json.dumps(llm_calls, ensure_ascii=False)
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO trace_log (ts,source,student_id,student,stage,event,intent,"
            "confidence,mode,card,freedom,reason,draft,guard,blocked,touch_count,"
            "next_stage,next_goal,llm_calls) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (record.get("ts"), source, record.get("student_id"), record.get("student"),
             record.get("stage"), record.get("event"), record.get("intent"),
             record.get("confidence"), record.get("mode"), record.get("card"),
             record.get("freedom"), record.get("reason"), record.get("draft"),
             record.get("guard"), record.get("blocked"), record.get("touch_count"),
             record.get("next_stage"), record.get("next_goal"), llm_calls))
        conn.commit()
    finally:
        conn.close()


def tail_trace(n: int = 200, source: str = None) -> list:
    _init()
    conn = _conn()
    try:
        if source:
            rows = conn.execute(
                "SELECT * FROM trace_log WHERE source=? ORDER BY id DESC LIMIT ?",
                (source, n)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trace_log ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM trace_log LIMIT 1").description]
    finally:
        conn.close()
    out = [dict(zip(cols, r)) for r in rows]
    out.reverse()   # 恢复成时间正序，和 jsonl 的阅读习惯一致
    for r in out:
        try:
            r["llm_calls"] = json.loads(r.get("llm_calls") or "[]")
        except Exception:
            r["llm_calls"] = []
    return out


def clear_trace(source: str = None):
    _init()
    conn = _conn()
    try:
        if source:
            conn.execute("DELETE FROM trace_log WHERE source=?", (source,))
        else:
            conn.execute("DELETE FROM trace_log")
        conn.commit()
    finally:
        conn.close()


_init()
