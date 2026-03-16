from flask import session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from db import get_conn

def get_board_role(board_id):
    """Вернуть роль текущего пользователя для доски: 'owner' или None."""
    user = current_user()
    if user is None:
        return None

    conn = get_conn()
    board = conn.execute(
        "SELECT owner_id FROM boards WHERE id = ?",
        (board_id,),
    ).fetchone()
    conn.close()

    if board is None:
        return None

    if board["owner_id"] == user["id"]:
        return "owner"

    # Позже сюда можно будет добавить проверки для приглашённых участников
    return None

def can_view_board(board_id):
    """Можно ли просматривать эту доску."""
    return get_board_role(board_id) is not None


def can_edit_board(board_id):
    """Можно ли редактировать доску (менять название, добавлять колонки и карточки)."""
    role = get_board_role(board_id)
    return role == "owner"


def is_board_owner(board_id):
    """Является ли текущий пользователь владельцем доски."""
    return get_board_role(board_id) == "owner"    

def create_user(username, password, role):
    """
    Создать пользователя с указанным логином, паролем и ролью.
    На этом этапе пароль сохраняется как есть (будем улучшать позже).
    """
    password_hash = generate_password_hash(password)

    conn = get_conn()
    conn.execute(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
        (username, password_hash, role),
    )
    conn.commit()
    conn.close()

def ensure_master():
    """
    Убедиться, что в системе есть хотя бы один администратор.
    Если нет — создать пользователя master/master с ролью admin.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM users WHERE role = 'admin' AND archived_at IS NULL LIMIT 1"
    ).fetchone()

    if row is None:
        create_user("master", "master", "admin")

    conn.close()

def is_logged_in():
    return session.get("user_id") is not None  

def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None

    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ? AND archived_at IS NULL",
        (user_id,),
    ).fetchone()
    conn.close()

    return user

def is_admin():
    user = current_user()
    return user is not None and user["role"] == "admin"

def get_registration_open():
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'registration_open'").fetchone()
    conn.close()
    return row is not None and row["value"] == "1" 