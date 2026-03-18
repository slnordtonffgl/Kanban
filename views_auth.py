from flask import render_template, request, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
from db import get_conn
from datetime import datetime
from views_boards import boards_for_user, collaborator_boards_for_user, archived_boards_for_user

def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE id = ? AND archived_at IS NULL", (user_id,)).fetchone()
    conn.close()
    return user

def is_logged_in():
    return current_user() is not None

def is_admin():
    user = current_user()
    return user is not None and user.get("role") == "admin"

def get_registration_open():
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'registration_open'").fetchone()
    conn.close()
    return row is not None and row["value"] == "1"

def login_form_view():
    if is_logged_in():
        return redirect(url_for("home"))
    # На этом шаге сессией ещё не пользуемся — просто показываем форму
    return render_template("login.html", error=None)

def login_view():
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

def logout_view():
    session.clear()
    return redirect(url_for("home"))

def register_form_view():
    if session.get("user_id") is not None:
        return redirect(url_for("dashboard"))
    if not get_registration_open():
        return render_template("register.html", registration_disabled=True), 403
    return render_template("register.html")

def register_view():
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
            "INSERT INTO users (username, password, role) VALUES (?, ?, 'user')",
            (username, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template("register.html", error="Username already taken."), 409
    conn.close()
    return redirect(url_for("login_form"))

def dashboard_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    user = current_user()
    if user is None:
        session.clear()
        return redirect(url_for("login_form"))

    boards = boards_for_user()
    collaborator_boards = collaborator_boards_for_user()
    archived_boards = archived_boards_for_user()

    return render_template(
        "dashboard.html",
        user=user,
        boards=boards,
        collaborator_boards=collaborator_boards,
        archived_boards=archived_boards,
    )
