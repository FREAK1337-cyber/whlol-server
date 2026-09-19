# app.py v1.0.1
import os
import sqlite3
import json
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for, g
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "whlol-secret-2026")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "whlol_admin_2026")

DB_PATH = "/tmp/whlol.db"


# ============================================================
# БАЗА ДАННЫХ
# ============================================================
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            hwid TEXT PRIMARY KEY,
            pc_name TEXT,
            first_seen TEXT,
            last_seen TEXT,
            banned INTEGER DEFAULT 0
        )
    """)
    db.commit()
    db.close()


# ============================================================
# АВТОРИЗАЦИЯ АДМИНА
# ============================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("user", "")
        pwd  = request.form.get("pass", "")
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Неверный логин или пароль"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ============================================================
# API — ДЛЯ ЛАУНЧЕРА
# ============================================================
@app.route("/api/register", methods=["POST"])
def api_register():
    """Лаунчер отправляет HWID + имя ПК при запуске."""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"ok": False, "error": "bad json"}), 400

    hwid = (data.get("hwid") or "").strip().upper()
    pc_name = (data.get("pc_name") or "unknown").strip()

    if not hwid:
        return jsonify({"ok": False, "error": "no hwid"}), 400

    now = datetime.utcnow().isoformat()
    db = get_db()

    row = db.execute("SELECT * FROM users WHERE hwid = ?", (hwid,)).fetchone()

    if row is None:
        db.execute(
            "INSERT INTO users (hwid, pc_name, first_seen, last_seen, banned) "
            "VALUES (?, ?, ?, ?, 0)",
            (hwid, pc_name, now, now)
        )
        db.commit()
        return jsonify({"ok": True, "banned": False, "new": True})

    db.execute(
        "UPDATE users SET last_seen = ?, pc_name = ? WHERE hwid = ?",
        (now, pc_name, hwid)
    )
    db.commit()
    return jsonify({"ok": True, "banned": bool(row["banned"])})


@app.route("/api/check_ban", methods=["GET"])
def api_check_ban():
    """Лаунчер проверяет бан по HWID."""
    hwid = (request.args.get("hwid") or "").strip().upper()
    if not hwid:
        return jsonify({"ok": False, "error": "no hwid"}), 400

    db = get_db()
    row = db.execute("SELECT banned FROM users WHERE hwid = ?", (hwid,)).fetchone()
    if row is None:
        return jsonify({"ok": True, "banned": False})

    return jsonify({"ok": True, "banned": bool(row["banned"])})


# ============================================================
# АДМИН-ПАНЕЛЬ
# ============================================================
@app.route("/admin")
@login_required
def admin():
    return render_template("admin.html")


@app.route("/api/users", methods=["GET"])
@login_required
def api_users():
    """Список всех пользователей."""
    db = get_db()
    rows = db.execute(
        "SELECT hwid, pc_name, first_seen, last_seen, banned "
        "FROM users ORDER BY last_seen DESC"
    ).fetchall()

    users = []
    for r in rows:
        users.append({
            "hwid": r["hwid"],
            "pc_name": r["pc_name"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
            "banned": bool(r["banned"]),
        })
    return jsonify({"ok": True, "users": users})


@app.route("/api/ban", methods=["POST"])
@login_required
def api_ban():
    data = request.get_json(force=True)
    hwid = (data.get("hwid") or "").strip().upper()
    if not hwid:
        return jsonify({"ok": False}), 400

    db = get_db()
    db.execute("UPDATE users SET banned = 1 WHERE hwid = ?", (hwid,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/unban", methods=["POST"])
@login_required
def api_unban():
    data = request.get_json(force=True)
    hwid = (data.get("hwid") or "").strip().upper()
    if not hwid:
        return jsonify({"ok": False}), 400

    db = get_db()
    db.execute("UPDATE users SET banned = 0 WHERE hwid = ?", (hwid,))
    db.commit()
    return jsonify({"ok": True})


# ============================================================
# ЗАПУСК
# ============================================================
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
