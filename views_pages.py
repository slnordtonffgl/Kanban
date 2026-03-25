from flask import render_template, request, redirect, url_for, flash
from db import get_conn
from auth_utils import is_logged_in, current_user
import re


def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-а-яё]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "page"


def _ensure_unique_slug(conn, slug: str) -> str:
    base = slug
    i = 1
    while True:
        row = conn.execute("SELECT 1 FROM pages WHERE slug = ? LIMIT 1", (slug,)).fetchone()
        if row is None:
            return slug
        i += 1
        slug = f"{base}-{i}"


def get_latest_approved_revision(conn, page_id: int):
    return conn.execute(
        """
        SELECT id, page_id, author_id, content, status, reviewer_id, review_note, rollback_reason, created_at
        FROM revisions
        WHERE page_id = ? AND status = 'approved'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (page_id,),
    ).fetchone()


def get_page_by_slug(slug: str):
    conn = get_conn()
    page = conn.execute(
        """
        SELECT
            p.id, p.title, p.slug, p.author_id, p.is_locked, p.created_at,
            u.username AS author_username
        FROM pages p
        LEFT JOIN users u ON p.author_id = u.id
        WHERE p.slug = ?
        """,
        (slug,),
    ).fetchone()
    if page is None:
        conn.close()
        return None

    page = dict(page)
    rev = get_latest_approved_revision(conn, page["id"])
    conn.close()

    if rev is not None:
        page["content"] = rev["content"]
        page["revision_created_at"] = rev["created_at"]
    else:
        page["content"] = None
        page["revision_created_at"] = None
    return page


def page_list_view():
    conn = get_conn()
    pages = conn.execute(
        """
        SELECT DISTINCT p.id, p.title, p.slug, p.created_at
        FROM pages p
        INNER JOIN revisions r ON r.page_id = p.id AND r.status = 'approved'
        ORDER BY p.title
        """
    ).fetchall()
    conn.close()
    return render_template("page_list.html", pages=pages)


def page_create_view():
    if not is_logged_in():
        return redirect(url_for("login_form"))

    title = (request.form.get("title") or "").strip()
    content = request.form.get("content") or ""
    if not title:
        return render_template("page_new.html", error="Введите заголовок.")

    conn = get_conn()
    slug = _ensure_unique_slug(conn, _slugify(title))
    user = current_user()

    cur = conn.execute(
        "INSERT INTO pages (title, slug, author_id) VALUES (?, ?, ?)",
        (title, slug, user["id"]),
    )
    page_id = cur.lastrowid

    status = "approved" if user["role"] == "admin" else "draft"
    conn.execute(
        "INSERT INTO revisions (page_id, author_id, content, status) VALUES (?, ?, ?, ?)",
        (page_id, user["id"], content, status),
    )
    conn.commit()
    conn.close()

    flash("Страница создана.")
    return redirect(url_for("page_view", slug=slug))