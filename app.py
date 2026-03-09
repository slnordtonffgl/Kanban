from werkzeug.security import check_password_hash, generate_password_hash
from flask import Flask, render_template,session,request,url_for, redirect,abort,flash 
import sqlite3
from datetime import datetime
from db import get_conn, init_db, insert_test_user, show_table


    




def is_agent():
    user = current_user()
    return user is not None and user["role"] == "agent"

def get_registration_open():
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'registration_open'").fetchone()
    conn.close()
    return row is not None and row["value"] == "1"    

@app.get("/login")
def login_form():
    if is_logged_in():
        return redirect(url_for("home"))

    # На этом шаге сессией ещё не пользуемся — просто показываем форму
    return render_template("login.html", error=None)


@app.post("/login")
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template(
            "login.html",
            error="Введите логин и пароль.",
        )

    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND archived_at IS NULL LIMIT 1",
        (username,),
    ).fetchone()
    conn.close()

    if user is None:
        return render_template(
            "login.html",
            error="Пользователь не найден.",
        )

    if not check_password_hash(user["password"], password):
        return render_template(
            "login.html",
            error="Неверный пароль.",
        )

    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]

    # Теперь после входа отправляем пользователя в дашборд
    return redirect(url_for("dashboard"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/")
def home():
    if not is_logged_in():
        return redirect(url_for("login_form"))
    conn = get_conn()
    row = conn.execute("SELECT 1 AS ok").fetchone()
    conn.close()

    db_ok = row is not None and row["ok"] == 1
    user = current_user()

    return render_template("home.html", db_ok=db_ok)

@app.get("/dashboard")
def dashboard():
    if not is_logged_in():
        # next=request.url — чтобы при желании можно было потом вернуть пользователя обратно
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    if user is None:
        # На всякий случай: если user_id в сессии битый
        session.clear()
        return redirect(url_for("login_form"))

    return render_template("dashboard.html", user=user) 

@app.get("/admin/settings")
def admin_settings():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)
    return render_template("admin_settings.html", registration_open=get_registration_open())


@app.post("/admin/settings")
def admin_settings_save():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)
    open_val = "1" if request.form.get("registration_open") == "on" else "0"
    conn = get_conn()
    conn.execute("REPLACE INTO settings (key, value) VALUES ('registration_open', ?)", (open_val,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_settings"))

@app.get("/admin/users")
def admin_users():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    conn = get_conn()
    users = conn.execute(
        """
        SELECT id, username, role, archived_at, created_at
        FROM users
        ORDER BY archived_at IS NULL DESC, username
        """
    ).fetchall()
    conn.close()

    return render_template("admin_users.html", users=users)    

@app.get("/register")
def register_form():
    if session.get("user_id") is not None:
        return redirect(url_for("dashboard"))
    if not get_registration_open():
        return render_template("register.html", registration_disabled=True), 403
    return render_template("register.html")

@app.post("/admin/users/create")
def admin_user_create():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not username or not password:
        flash("Введите логин и пароль.")
        return redirect(url_for("admin_users"))

    if len(username) < 2:
        flash("Логин слишком короткий.")
        return redirect(url_for("admin_users"))

    try:
        # В универсальном варианте создаём пользователей с ролью 'user'
        create_user(username, password, "user")
        flash(f"Пользователь {username} создан.")
    except sqlite3.IntegrityError:
        flash("Такой логин уже занят.")

    return redirect(url_for("admin_users"))

@app.post("/admin/users/<int:user_id>/archive")
def admin_user_archive(user_id):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    conn = get_conn()
    u = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if u is None:
        conn.close()
        abort(404)

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute("UPDATE users SET archived_at = ? WHERE id = ?", (now, user_id))
    conn.commit()
    conn.close()

    flash("Пользователь заархивирован. Он больше не сможет войти.")
    return redirect(url_for("admin_users"))

@app.post("/admin/users/<int:user_id>/restore")
def admin_user_restore(user_id):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    conn = get_conn()
    u = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if u is None:
        conn.close()
        abort(404)

    conn.execute("UPDATE users SET archived_at = NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash("Пользователь восстановлен.")
    return redirect(url_for("admin_users")) 

@app.post("/admin/users/<int:user_id>/delete")
def admin_user_delete(user_id):
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    if not is_admin():
        abort(403)

    conn = get_conn()
    u = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if u is None:
        conn.close()
        abort(404)

    if u["role"] == "admin":
        # Мастер‑аккаунт удалять нельзя
        conn.close()
        flash("Нельзя удалить мастер‑аккаунт.")
        return redirect(url_for("admin_users"))

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash(f"Пользователь {u['username']} удалён безвозвратно.")
    return redirect(url_for("admin_users"))

@app.post("/register")
def register():
    if not get_registration_open():
        return render_template("register.html", registration_disabled=True), 403
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    if not username or not password:
        return render_template("register.html", error="Username and password required."), 400
    if len(username) < 2:
        return render_template("register.html", error="Username too short."), 400
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, 'user')"
,
            (username, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template("register.html", error="Username already taken."), 409
    conn.close()
    return redirect(url_for("login_form")) 

@app.context_processor
def inject():
    return {
        "current_user": current_user,
        "is_admin": is_admin,
        #"is_agent": is_agent,
        "registration_open": get_registration_open(),
    }
    



if __name__ == "__main__":
    init_db()          # создаём таблицу, если её ещё нет
    ensure_master()
    insert_test_user() # временно: добавим одного пользователя для проверки

    # По желанию: посмотреть содержимое таблицы в консоли
    print(show_table())



    app.run(debug=True)   


