from flask import render_template, redirect, url_for, request, abort
from db import get_conn
from auth_utils import is_logged_in, current_user, can_view_board, is_board_owner

def boards_for_user():
    """Вернуть активные доски текущего пользователя."""
    user = current_user()
    if user is None:
        return []

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, title, description, is_archived, created_at
        FROM boards
        WHERE owner_id = ? AND is_archived = 0
        ORDER BY created_at DESC
        """,
        (user["id"],),
    ).fetchall()
    conn.close()

    return rows
def board_new_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    return render_template("board_new.html", error=None)


def board_create_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not title:
        return render_template("board_new.html", error="Введите название доски.")

    user = current_user()

    conn = get_conn()
    conn.execute(
        "INSERT INTO boards (owner_id, title, description) VALUES (?, ?, ?)",
        (user["id"], title, description or ""),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))   

def cards_for_board(board_id: int):
    """Вернуть все карточки доски, сгруппированные по колонкам."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.column_id,
            c.title,
            c.description,
            c.position,
            c.created_by,
            c.created_at,
            c.updated_at
        FROM cards c
        JOIN columns col ON c.column_id = col.id
        WHERE col.board_id = ?
        ORDER BY c.position ASC, c.id ASC
        """,
        (board_id,),
    ).fetchall()
    conn.close()

    by_column = {}
    for row in rows:
        by_column.setdefault(row["column_id"], []).append(row)

    return by_column


def board_view_view(board_id: int):
    # ... существующий код ...
    
    columns = columns_for_board(board_id)
    cards_by_column = cards_for_board(board_id)  # ← ДОБАВИТЬ
    can_edit = can_edit_board(board_id)

    return render_template(
        "board.html",
        board=board,
        columns=columns,
        cards_by_column=cards_by_column,  # ← ДОБАВИТЬ
        is_owner=is_board_owner(board_id),
        can_edit=can_edit,
    )

def count_cards_in_column(conn, column_id: int) -> int:
    """Подсчитать количество карточек в колонке (использует существующее соединение)."""
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM cards WHERE column_id = ?",
        (column_id,),
    ).fetchone()
    return row["cnt"] if row is not None else 0

def card_create_view(column_id: int):
    """Создать новую карточку в колонке."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    conn = get_conn()

    # Находим колонку и связанную доску
    column = conn.execute(
        "SELECT id, board_id, wip_limit FROM columns WHERE id = ?",
        (column_id,),
    ).fetchone()

    if column is None:
        conn.close()
        abort(404)

    board_id = column["board_id"]

    if not can_edit_board(board_id):
        conn.close()
        abort(404)

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not title:
        conn.close()
        return redirect(url_for("board_view", board_id=board_id))

    # Проверяем WIP‑лимит
    if column["wip_limit"] is not None and column["wip_limit"] > 0:
        current_count = count_cards_in_column(conn, column_id)
        if current_count >= column["wip_limit"]:
            conn.close()
            return redirect(url_for("board_view", board_id=board_id))

    user = current_user()

    # Находим следующий position
    row = conn.execute(
        "SELECT COALESCE(MAX(position), 0) AS max_pos FROM cards WHERE column_id = ?",
        (column_id,),
    ).fetchone()
    next_position = (row["max_pos"] or 0) + 1

    conn.execute(
        """
        INSERT INTO cards (column_id, title, description, position, created_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (column_id, title, description or "", next_position, user["id"]),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("board_view", board_id=board_id))

def card_edit_view(card_id: int):
    """Изменить заголовок и описание карточки."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    conn = get_conn()

    card = conn.execute(
        """
        SELECT c.id, c.column_id, c.title, c.description, col.board_id
        FROM cards c
        JOIN columns col ON c.column_id = col.id
        WHERE c.id = ?
        """,
        (card_id,),
    ).fetchone()

    if card is None:
        conn.close()
        abort(404)

    board_id = card["board_id"]

    if not can_edit_board(board_id):
        conn.close()
        abort(404)

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not title:
        conn.close()
        return redirect(url_for("board_view", board_id=board_id))

    conn.execute(
        """
        UPDATE cards
        SET title = ?, description = ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        WHERE id = ?
        """,
        (title, description or "", card_id),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("board_view", board_id=board_id))
