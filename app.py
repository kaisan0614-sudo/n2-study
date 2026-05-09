import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
import db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "n2study_secret")

db.init_db()
db.seed_data()


@app.route("/")
def index():
    db.log_session()
    stats = db.get_dashboard_stats()
    current_day = db.get_current_day()
    return render_template("index.html", stats=stats, current_day=current_day)


@app.route("/vocab")
def vocab():
    db.log_session()
    day = request.args.get("day", None, type=int)
    if day is None:
        day = db.get_current_day()
    vocab_list = db.get_vocab_for_day(day)
    total_days = db.get_total_days()
    return render_template("vocab.html", vocab_list=vocab_list, day=day, total_days=total_days)


@app.route("/quiz")
def quiz_home():
    return render_template("quiz_home.html")


@app.route("/quiz/<quiz_type>")
def quiz(quiz_type):
    valid = {"kanji", "grammar", "listening", "reading"}
    if quiz_type not in valid:
        return redirect(url_for("quiz_home"))
    questions = db.get_questions(quiz_type)
    type_names = {
        "kanji": "漢字讀音",
        "grammar": "語法選擇",
        "listening": "聽力理解",
        "reading": "閱讀理解",
    }
    return render_template("quiz.html", questions=questions,
                           quiz_type=quiz_type, type_name=type_names[quiz_type])


@app.route("/stats")
def stats():
    stats_data = db.get_full_stats()
    return render_template("stats.html", stats=stats_data)


@app.route("/api/vocab/status", methods=["POST"])
def api_vocab_status():
    data = request.get_json()
    db.update_vocab_status(data["vocab_id"], data["status"])
    return jsonify({"success": True})


@app.route("/api/quiz/submit", methods=["POST"])
def api_quiz_submit():
    result = db.record_quiz_attempts(request.get_json())
    return jsonify(result)


@app.route("/api/backup", methods=["POST"])
def api_backup():
    filename = db.create_backup()
    return jsonify({"success": True, "filename": filename})


@app.route("/api/import", methods=["POST"])
def api_import():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file"}), 400
    result = db.import_vocab_csv(f)
    return jsonify(result)


if __name__ == "__main__":
    print("🎌 N2 日文學習系統啟動中...")
    print("   本機：http://127.0.0.1:5000")
    print("   區域網路：http://192.168.50.5:5000")
    app.run(host="0.0.0.0", debug=True, port=5000)
