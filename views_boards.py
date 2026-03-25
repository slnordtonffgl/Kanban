from flask import render_template, redirect, url_for, request, abort
from db import get_conn
from auth_utils import is_logged_in, current_user, can_view_board, is_board_owner, can_edit_board

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

def board_archive_view(board_id: int):
    """Архивировать доску (только владелец)."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    if not is_board_owner(board_id):
        abort(404)

    conn = get_conn()
    conn.execute(
        "UPDATE boards SET is_archived = 1 WHERE id = ?",
        (board_id,),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


def board_restore_view(board_id: int):
    """Разархивировать доску (только владелец)."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    if not is_board_owner(board_id):
        abort(404)

    conn = get_conn()
    conn.execute(
        "UPDATE boards SET is_archived = 0 WHERE id = ?",
        (board_id,),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("board_view", board_id=board_id))

def board_new_view():
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    return render_template("board_new.html", error=None)

def collaborator_boards_for_user():
    """Вернуть активные доски, где текущий пользователь — приглашённый участник."""
    user = current_user()
    if user is None:
        return []

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT
            b.id, b.title, b.description, b.is_archived, b.created_at,
            c.role AS collab_role
        FROM boards b
        JOIN collaborators c ON c.board_id = b.id
        WHERE c.user_id = ? AND b.is_archived = 0
        ORDER BY b.created_at DESC
        """,
        (user["id"],),
    ).fetchall()
    conn.close()
    return rows

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

def board_delete_view(board_id: int):
    """Полностью удалить доску и все связанные данные (только владелец)."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    if not is_board_owner(board_id):
        abort(404)

    conn = get_conn()

    # Находим все колонки и карточки этой доски
    columns = conn.execute(
        "SELECT id FROM columns WHERE board_id = ?",
        (board_id,),
    ).fetchall()
    column_ids = [col["id"] for col in columns]

    card_ids = []
    if column_ids:
        rows = conn.execute(
            "SELECT id FROM cards WHERE column_id IN ({})".format(
                ",".join("?" for _ in column_ids)
            ),
            column_ids,
        ).fetchall()
        card_ids = [r["id"] for r in rows]

    # Удаляем активность по карточкам
    if card_ids:
        conn.execute(
            "DELETE FROM card_activity WHERE card_id IN ({})".format(
                ",".join("?" for _ in card_ids)
            ),
            card_ids,
        )

    # Удаляем карточки и колонки
    if column_ids:
        conn.execute(
            "DELETE FROM cards WHERE column_id IN ({})".format(
                ",".join("?" for _ in column_ids)
            ),
            column_ids,
        )
        conn.execute(
            "DELETE FROM columns WHERE board_id = ?",
            (board_id,),
        )

    # Удаляем участников
    conn.execute(
        "DELETE FROM collaborators WHERE board_id = ?",
        (board_id,),
    )

    # Удаляем саму доску
    conn.execute(
        "DELETE FROM boards WHERE id = ?",
        (board_id,),
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
            c.id, c.column_id, c.title, c.description, c.position,
            c.created_by, c.created_at, c.updated_at
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

def archived_boards_for_user():
    """Вернуть доски пользователя, которые находятся в архиве (где он владелец или участник)."""
    user = current_user()
    if user is None:
        return []

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT DISTINCT
            b.id,
            b.title,
            b.description,
            b.is_archived,
            b.created_at
        FROM boards b
        LEFT JOIN collaborators c
            ON c.board_id = b.id
        WHERE
            b.is_archived = 1
            AND (
                b.owner_id = ?
                OR c.user_id = ?
            )
        ORDER BY b.created_at DESC
        """,
        (user["id"], user["id"]),
    ).fetchall()
    conn.close()

    return rows

def board_view_view(board_id: int):
    conn = get_conn()
    board = conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
    if board is None:
        conn.close()
        abort(404)

    if not can_view_board(board_id):
        conn.close()
        abort(404)

    columns = conn.execute(
        """
        SELECT id, board_id, title, position, wip_limit
        FROM columns
        WHERE board_id = ?
        ORDER BY position ASC, id ASC
        """,
        (board_id,),
    ).fetchall()
    conn.close()

    cards_by_column = cards_for_board(board_id)
    collaborators = []  # можно добавить позже
    activity = recent_activity_for_board(board_id)
    can_edit = can_edit_board(board_id)

    return render_template(
        "board.html",
        board=board,
        columns=columns,
        cards_by_column=cards_by_column,
        collaborators=collaborators,
        activity=activity,
        is_owner=is_board_owner(board_id),
        can_edit=can_edit,
    )

def count_cards_in_column(conn, column_id: int) -> int:
    """Подсчитать количество карточек в колонке."""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM cards WHERE column_id = ?", (column_id,)).fetchone()
    return row["cnt"] if row else 0

def card_create_view(column_id: int):
    """Создать новую карточку в колонке."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    conn = get_conn()
    column = conn.execute("SELECT id, board_id, wip_limit FROM columns WHERE id = ?", (column_id,)).fetchone()

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
    if column["wip_limit"] and column["wip_limit"] > 0:
        current_count = count_cards_in_column(conn, column_id)
        if current_count >= column["wip_limit"]:
            conn.close()
            return redirect(url_for("board_view", board_id=board_id))

    user = current_user()
    row = conn.execute("SELECT COALESCE(MAX(position), 0) AS max_pos FROM cards WHERE column_id = ?", (column_id,)).fetchone()
    next_position = (row["max_pos"] or 0) + 1

    cur = conn.execute(
        """
        INSERT INTO cards (column_id, title, description, position, created_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (column_id, title, description or "", next_position, user["id"]),
    )
    card_id = cur.lastrowid

    _log_activity(conn, card_id=card_id, user_id=user["id"], action_type="created", from_column_id=None, to_column_id=column_id)

    conn.commit()
    conn.close()

    return redirect(url_for("board_view", board_id=board_id))

def collaborator_add_view(board_id: int):
    """Добавить участника к доске (только владелец)."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    if not is_board_owner(board_id):
        abort(404)

    user_id_raw = request.form.get("user_id")
    role = (request.form.get("role") or "").strip()

    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        return redirect(url_for("board_view", board_id=board_id))

    if role not in ("viewer", "editor"):
        return redirect(url_for("board_view", board_id=board_id))

    conn = get_conn()
    board = conn.execute("SELECT owner_id FROM boards WHERE id = ?", (board_id,)).fetchone()

    if board is None or board["owner_id"] == user_id:
        conn.close()
        return redirect(url_for("board_view", board_id=board_id))

    user = conn.execute("SELECT id FROM users WHERE id = ? AND archived_at IS NULL", (user_id,)).fetchone()
    if user is None:
        conn.close()
        return redirect(url_for("board_view", board_id=board_id))

    conn.execute(
        "INSERT OR IGNORE INTO collaborators (board_id, user_id, role) VALUES (?, ?, ?)",
        (board_id, user_id, role),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("board_view", board_id=board_id))

def collaborator_remove_view(board_id: int):
    """Удалить участника с доски (только владелец)."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    if not is_board_owner(board_id):
        abort(404)

    user_id_raw = request.form.get("user_id")
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        return redirect(url_for("board_view", board_id=board_id))

    conn = get_conn()
    conn.execute("DELETE FROM collaborators WHERE board_id = ? AND user_id = ?", (board_id, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for("board_view", board_id=board_id))

def card_edit_view(card_id: int):
    """Изменить карточку."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    conn = get_conn()
    card = conn.execute(
        "SELECT c.id, c.column_id, col.board_id FROM cards c JOIN columns col ON c.column_id = col.id WHERE c.id = ?",
        (card_id,),
    ).fetchone()

    if card is None or not can_edit_board(card["board_id"]):
        conn.close()
        abort(404)

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not title:
        conn.close()
        return redirect(url_for("board_view", board_id=card["board_id"]))

    conn.execute(
        """
        UPDATE cards
        SET title = ?, description = ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        WHERE id = ?
        """,
        (title, description or "", card_id),
    )

    user = current_user()
    if user:
        _log_activity(conn, card_id=card_id, user_id=user["id"], action_type="edited")

    conn.commit()
    conn.close()

    return redirect(url_for("board_view", board_id=card["board_id"]))

def recent_activity_for_board(board_id: int, limit: int = 30):
    """Вернуть последние события по карточкам этой доски."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT
            a.id,
            a.card_id,
            a.user_id,
            a.action_type,
            a.from_column_id,
            a.to_column_id,
            a.created_at,
            u.username AS user_username,
            c.title AS card_title,
            col_from.title AS from_column_name,
            col_to.title AS to_column_name
        FROM card_activity a
        JOIN cards c ON a.card_id = c.id
        JOIN users u ON a.user_id = u.id
        JOIN columns col_card ON c.column_id = col_card.id
        JOIN boards b ON col_card.board_id = b.id
        LEFT JOIN columns col_from ON a.from_column_id = col_from.id
        LEFT JOIN columns col_to ON a.to_column_id = col_to.id
        WHERE b.id = ?
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT ?
        """,
        (board_id, limit),
    ).fetchall()
    conn.close()

    return rows

def card_move_view(card_id: int):
    """Перенести карточку в другую колонку (в пределах одной доски)."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))

    conn = get_conn()

    # Загружаем карточку и связанную доску
    card = conn.execute(
        """
        SELECT
            c.id,
            c.column_id,
            col.board_id
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

    current_column_id = card["column_id"]
    new_column_id = request.form.get("new_column_id")

    try:
        new_column_id = int(new_column_id)
    except (TypeError, ValueError):
        conn.close()
        return redirect(url_for("board_view", board_id=board_id))

    if new_column_id == current_column_id:
        conn.close()
        return redirect(url_for("board_view", board_id=board_id))

    # Проверяем, что новая колонка принадлежит той же доске
    new_column = conn.execute(
        "SELECT id, board_id, wip_limit FROM columns WHERE id = ?",
        (new_column_id,),
    ).fetchone()

    if new_column is None or new_column["board_id"] != board_id:
        conn.close()
        abort(404)

    # Если у целевой колонки есть WIP‑лимит и карточка ещё не там — проверяем количество
    if new_column["wip_limit"] is not None and new_column["wip_limit"] > 0:
        current_count = count_cards_in_column(conn, new_column_id)
        if current_count >= new_column["wip_limit"]:
            conn.close()
            # Позже можно заменить на flash с текстом "Target column WIP limit reached"
            return redirect(url_for("board_view", board_id=board_id))

    # Помещаем карточку в конец списка целевой колонки
    row = conn.execute(
        "SELECT COALESCE(MAX(position), 0) AS max_pos FROM cards WHERE column_id = ?",
        (new_column_id,),
    ).fetchone()
    next_position = (row["max_pos"] or 0) + 1

    conn.execute(
        """
        UPDATE cards
        SET column_id = ?, position = ?, updated_at = (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        WHERE id = ?
        """,
        (new_column_id, next_position, card_id),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("board_view", board_id=board_id))

def _log_activity(conn, card_id: int, user_id: int, action_type: str, from_column_id=None, to_column_id=None):
    """Залогировать действие с карточкой в таблице card_activity."""
    if action_type not in ("created", "edited", "moved"):
        return

    conn.execute(
        """
        INSERT INTO card_activity (card_id, user_id, action_type, from_column_id, to_column_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (card_id, user_id, action_type, from_column_id, to_column_id),
    )


def column_create_view(board_id: int):
    """Создать новую колонку."""
    if not is_logged_in():
        return redirect(url_for("login_form", next=request.url))
    
    if not can_edit_board(board_id):
        abort(404)
    
    title = (request.form.get("title") or "").strip()
    wip_limit_str = request.form.get("wip_limit", "")
    wip_limit = int(wip_limit_str) if wip_limit_str.isdigit() else None
    
    if not title:
        return redirect(url_for("board_view", board_id=board_id))
    
    conn = get_conn()
    row = conn.execute("SELECT COALESCE(MAX(position), 0) AS max_pos FROM columns WHERE board_id = ?", (board_id,)).fetchone()
    position = (row["max_pos"] or 0) + 1
    
    conn.execute(
        "INSERT INTO columns (board_id, title, position, wip_limit) VALUES (?, ?, ?, ?)",
        (board_id, title, position, wip_limit)
    )
    conn.commit()
    conn.close()
    
    return redirect(url_for("board_view", board_id=board_id))
