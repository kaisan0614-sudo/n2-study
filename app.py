import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "n2study_secret")

db.init_db()
db.seed_data()


@app.before_request
def require_user():
    public = {'select_user', 'choose_user', 'add_user', 'static'}
    if request.endpoint not in public and 'user_id' not in session:
        return redirect(url_for('select_user'))


@app.route("/select")
def select_user():
    users = db.get_users()
    return render_template("select_user.html", users=users)


@app.route("/select/<int:user_id>")
def choose_user(user_id):
    users = db.get_users()
    user = next((u for u in users if u['id'] == user_id), None)
    if user:
        session['user_id'] = user_id
        session['user_name'] = user['name']
    return redirect(url_for('index'))


@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form.get("name", "").strip()
    if name:
        new_id = db.create_user(name)
        if new_id:
            session['user_id'] = new_id
            session['user_name'] = name
            return redirect(url_for('index'))
    return redirect(url_for('select_user'))


@app.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if session.get('user_id') == user_id:
        session.clear()
    db.delete_user(user_id)
    return redirect(url_for('select_user'))


@app.route("/switch")
def switch_user():
    session.clear()
    return redirect(url_for('select_user'))


@app.route("/")
def index():
    user_id = session['user_id']
    db.log_session(user_id)
    stats = db.get_dashboard_stats(user_id)
    current_day = db.get_current_day(user_id)
    return render_template("index.html", stats=stats, current_day=current_day)


@app.route("/vocab")
def vocab():
    user_id = session['user_id']
    db.log_session(user_id)
    day = request.args.get("day", None, type=int)
    if day is None:
        day = db.get_current_day(user_id)
    vocab_list = db.get_vocab_for_day(day, user_id)
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
    user_id = session['user_id']
    stats_data = db.get_full_stats(user_id)
    return render_template("stats.html", stats=stats_data)


@app.route("/api/vocab/status", methods=["POST"])
def api_vocab_status():
    data = request.get_json()
    db.update_vocab_status(data["vocab_id"], data["status"], session['user_id'])
    return jsonify({"success": True})


@app.route("/api/quiz/submit", methods=["POST"])
def api_quiz_submit():
    result = db.record_quiz_attempts(request.get_json(), session['user_id'])
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
    print("N2 日文學習系統啟動中...")
    print("   本機：http://127.0.0.1:5000")
    print("   區域網路：http://192.168.50.5:5000")
    app.run(host="0.0.0.0", debug=True, port=5000)
