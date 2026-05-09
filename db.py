import sqlite3
import os
import shutil
from datetime import datetime, date, timedelta

_default_db = os.path.join(os.path.dirname(__file__), "n2_study.db")
DB_PATH = os.environ.get("DB_PATH", _default_db)
BACKUP_DIR = os.path.dirname(DB_PATH)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji TEXT NOT NULL,
            reading TEXT NOT NULL,
            meaning TEXT NOT NULL,
            example_jp TEXT,
            example_zh TEXT,
            day_group INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS user_vocab_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vocab_id INTEGER UNIQUE,
            status TEXT DEFAULT 'new',
            review_count INTEGER DEFAULT 0,
            last_reviewed TIMESTAMP,
            FOREIGN KEY (vocab_id) REFERENCES vocabulary(id)
        );
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date DATE NOT NULL UNIQUE,
            vocab_studied INTEGER DEFAULT 0,
            quiz_taken INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            question_type TEXT,
            is_correct INTEGER,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            context TEXT,
            question TEXT NOT NULL,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            correct_answer TEXT NOT NULL,
            explanation TEXT
        );
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename TEXT
        );
    """)
    conn.commit()
    conn.close()


def seed_data():
    from data import VOCABULARY, QUESTIONS
    conn = get_db()
    c = conn.cursor()

    if c.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO vocabulary (kanji, reading, meaning, example_jp, example_zh, day_group) VALUES (?,?,?,?,?,?)",
            [(v["kanji"], v["reading"], v["meaning"], v["example_jp"], v["example_zh"], v["day_group"]) for v in VOCABULARY]
        )

    if c.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO questions (type,context,question,option_a,option_b,option_c,option_d,correct_answer,explanation) VALUES (?,?,?,?,?,?,?,?,?)",
            [(q["type"], q.get("context"), q["question"], q["option_a"], q["option_b"], q["option_c"], q["option_d"], q["correct_answer"], q.get("explanation")) for q in QUESTIONS]
        )

    conn.commit()
    conn.close()


def log_session():
    today = date.today().isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO study_sessions (session_date, vocab_studied, quiz_taken) VALUES (?,0,0)", (today,))
    conn.commit()
    conn.close()


def get_current_day():
    conn = get_db()
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
    max_day = c.execute("SELECT COALESCE(MAX(day_group),1) FROM vocabulary").fetchone()[0]
    conn.close()
    return min(max(count, 1), max_day)


def get_total_days():
    conn = get_db()
    c = conn.cursor()
    v = c.execute("SELECT COALESCE(MAX(day_group),1) FROM vocabulary").fetchone()[0]
    conn.close()
    return v


def get_vocab_for_day(day):
    conn = get_db()
    c = conn.cursor()
    rows = c.execute("""
        SELECT v.*, COALESCE(uvs.status, 'new') AS status
        FROM vocabulary v
        LEFT JOIN user_vocab_status uvs ON v.id = uvs.vocab_id
        WHERE v.day_group = ?
        ORDER BY v.id
    """, (day,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_vocab_status(vocab_id, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO user_vocab_status (vocab_id, status, review_count, last_reviewed)
        VALUES (?, ?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(vocab_id) DO UPDATE SET
            status = excluded.status,
            review_count = review_count + 1,
            last_reviewed = CURRENT_TIMESTAMP
    """, (vocab_id, status))
    today = date.today().isoformat()
    c.execute("UPDATE study_sessions SET vocab_studied = vocab_studied + 1 WHERE session_date = ?", (today,))
    conn.commit()
    conn.close()


def get_questions(quiz_type):
    conn = get_db()
    c = conn.cursor()
    rows = c.execute("SELECT * FROM questions WHERE type=? ORDER BY id", (quiz_type,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_quiz_attempts(data):
    answers = data.get("answers", {})
    conn = get_db()
    c = conn.cursor()

    details = []
    correct_count = 0

    for qid_str, user_ans in answers.items():
        q = c.execute("SELECT * FROM questions WHERE id=?", (int(qid_str),)).fetchone()
        if not q:
            continue
        is_correct = 1 if user_ans == q["correct_answer"] else 0
        if is_correct:
            correct_count += 1
        c.execute("INSERT INTO quiz_attempts (question_id, question_type, is_correct) VALUES (?,?,?)",
                  (q["id"], q["type"], is_correct))
        details.append({
            "question": q["question"],
            "your_answer": f"{user_ans.upper()}. {q['option_' + user_ans]}",
            "correct_answer": f"{q['correct_answer'].upper()}. {q['option_' + q['correct_answer']]}",
            "is_correct": bool(is_correct),
            "explanation": q["explanation"] or ""
        })

    today = date.today().isoformat()
    c.execute("UPDATE study_sessions SET quiz_taken = quiz_taken + 1 WHERE session_date = ?", (today,))
    conn.commit()
    conn.close()

    total = len(details)
    return {
        "correct": correct_count,
        "total": total,
        "percentage": round(correct_count / total * 100) if total else 0,
        "details": details
    }


def _consecutive_days(sessions):
    if not sessions:
        return 0
    today = date.today()
    dates = sorted([date.fromisoformat(s["session_date"]) for s in sessions], reverse=True)
    if not dates or dates[0] < today - timedelta(days=1):
        return 0
    count = 0
    expected = dates[0]
    for d in dates:
        if d == expected:
            count += 1
            expected -= timedelta(days=1)
        else:
            break
    return count


def get_dashboard_stats():
    conn = get_db()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
    mastered = c.execute("SELECT COUNT(*) FROM user_vocab_status WHERE status='mastered'").fetchone()[0]
    learning = c.execute("SELECT COUNT(*) FROM user_vocab_status WHERE status='learning'").fetchone()[0]
    sessions = c.execute("SELECT session_date FROM study_sessions ORDER BY session_date DESC").fetchall()
    total_q = c.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
    correct_q = c.execute("SELECT COUNT(*) FROM quiz_attempts WHERE is_correct=1").fetchone()[0]
    conn.close()
    return {
        "vocab_total": total,
        "vocab_mastered": mastered,
        "vocab_learning": learning,
        "vocab_new": total - mastered - learning,
        "consecutive_days": _consecutive_days(sessions),
        "quiz_accuracy": round(correct_q / total_q * 100, 1) if total_q else 0,
        "total_attempts": total_q,
        "mastery_pct": round(mastered / total * 100, 1) if total else 0,
    }


def get_full_stats():
    conn = get_db()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
    mastered = c.execute("SELECT COUNT(*) FROM user_vocab_status WHERE status='mastered'").fetchone()[0]
    learning = c.execute("SELECT COUNT(*) FROM user_vocab_status WHERE status='learning'").fetchone()[0]
    sessions = c.execute("SELECT session_date FROM study_sessions ORDER BY session_date DESC").fetchall()

    accuracy_by_type = {}
    for t in ["kanji", "grammar", "listening", "reading"]:
        tot = c.execute("SELECT COUNT(*) FROM quiz_attempts WHERE question_type=?", (t,)).fetchone()[0]
        cor = c.execute("SELECT COUNT(*) FROM quiz_attempts WHERE question_type=? AND is_correct=1", (t,)).fetchone()[0]
        accuracy_by_type[t] = round(cor / tot * 100, 1) if tot else 0

    weekly_data = []
    today = date.today()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        row = c.execute("SELECT vocab_studied, quiz_taken FROM study_sessions WHERE session_date=?", (d.isoformat(),)).fetchone()
        weekly_data.append({
            "date": d.strftime("%m/%d"),
            "studied": 1 if row else 0,
            "vocab": row["vocab_studied"] if row else 0,
            "quiz": row["quiz_taken"] if row else 0,
        })

    total_q = c.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
    correct_q = c.execute("SELECT COUNT(*) FROM quiz_attempts WHERE is_correct=1").fetchone()[0]
    conn.close()

    return {
        "vocab_total": total,
        "vocab_mastered": mastered,
        "vocab_learning": learning,
        "vocab_new": total - mastered - learning,
        "consecutive_days": _consecutive_days(sessions),
        "mastery_pct": round(mastered / total * 100, 1) if total else 0,
        "accuracy_by_type": accuracy_by_type,
        "weekly_data": weekly_data,
        "total_attempts": total_q,
        "correct_attempts": correct_q,
        "overall_accuracy": round(correct_q / total_q * 100, 1) if total_q else 0,
    }


def create_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{ts}.db"
    shutil.copy2(DB_PATH, os.path.join(BACKUP_DIR, filename))
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO backups (filename) VALUES (?)", (filename,))
    conn.commit()
    conn.close()
    return filename


def import_vocab_csv(file):
    import csv, io
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    conn = get_db()
    c = conn.cursor()
    max_day = c.execute("SELECT COALESCE(MAX(day_group),0) FROM vocabulary").fetchone()[0]
    new_day = max_day + 1
    count = 0
    for row in reader:
        if row.get("kanji"):
            c.execute(
                "INSERT INTO vocabulary (kanji,reading,meaning,example_jp,example_zh,day_group) VALUES (?,?,?,?,?,?)",
                (row.get("kanji",""), row.get("reading",""), row.get("meaning",""),
                 row.get("example_jp",""), row.get("example_zh",""), int(row.get("day_group", new_day)))
            )
            count += 1
    conn.commit()
    conn.close()
    return {"success": True, "imported": count}
