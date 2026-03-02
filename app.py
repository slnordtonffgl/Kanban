from werkzeug.security import check_password_hash, generate_password_hash
from flask import Flask, render_template,session,request,url_for, redirect

import sqlite3


app = Flask(__name__)
app.secret_key = "dev-secret"
DB_PATH = "database.db"

def current_user():
    """Возвращает строку текущего пользователя (dict-like) или None."""
    uid = session.get("user_id")
    if uid is None:
        return None
    conn = get_conn()
    user = conn.execute(
        "SELECT id, username, role FROM users WHERE id = ? AND archived_at IS NULL",
        (uid,),
    ).fetchone()
    conn.close()
    return user

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # строки как словари: row["column_name"]
    conn.execute("PRAGMA foreign_keys = ON")  # включить внешние ключи (пригодятся позже)
    return conn

@app.route("/")
def home():
    conn = get_conn()
    row = conn.execute("SELECT 1 AS ok").fetchone()
    rows = conn.execute("SELECT * FROM users")
    for r in rows:
        print(dict(r))
    conn.close()
    return render_template("index.html", db_ok=row is not None and row["ok"] == 1)

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
            archived_at TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)

    conn.commit()
    conn.close()

def ensure_master():
    """Создать пользователя master (admin), если ещё нет ни одного admin."""
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if row is not None:
        conn.close()
        return
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
        ("master", generate_password_hash("master")),
    )
    conn.commit()
    conn.close() 
@app.route("/login", methods=["GET", "POST"])
def login():
    # GET: форма входа
    if request.method == "GET":
        # Если уже авторизован - редирект на дашборд
        if session.get("user_id"):
            return redirect("/")
        next_url = request.args.get("next")
        return render_template("login.html", next=next_url)
    
    # POST: обработка формы
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    
    if not username or not password:
        return render_template("login.html", error="Введите логин и пароль.", next=request.args.get("next")), 400
    
    conn = get_conn()
    user = conn.execute(
        "SELECT id, password_hash, role FROM users WHERE username = ? AND archived_at IS NULL",
        (username,),
    ).fetchone()
    conn.close()
    
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Неверный логин или пароль.", next=request.args.get("next")), 401
    
    # Успешный вход
    session.clear()  # очищаем предыдущую сессию
    session["user_id"] = user["id"]
    session["role"] = user["role"]  # опционально
    
    next_url = request.form.get("next") or request.args.get("next") 
    "/"
    return redirect(next_url)

@app.get("/logout")
def logout():
    session.clear()
    return "/"
@app.get("/")
def home():
    conn = get_conn()
    row = conn.execute("SELECT 1 AS ok").fetchone()
    conn.close()
    return render_template(
        "home.html",
        db_ok=row is not None and row["ok"] == 1,
        current_user=current_user,
    )

    
if __name__ == "__main__":
    init_db()
    ensure_master()
    app.run(debug=True)    


