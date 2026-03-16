def get_page_by_slug(slug: str):
    """Найти страницу по slug; контент и дата ревизии — из последней утверждённой ревизии."""
    conn = get_conn()
    page = conn.execute(
        """
        SELECT
            p.id,
            p.title,
            p.slug,
            p.author_id,
            p.is_locked,
            p.created_at,
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

def get_latest_approved_revision(conn, page_id: int):
    """Вернуть последнюю ревизию страницы со статусом approved или None."""
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

def page_create_view()
        slug = slugify(title)
    slug = ensure_unique_slug(conn, slug)
    user = current_user()

    cursor = conn.execute(
        "INSERT INTO pages (title, slug, author_id) VALUES (?, ?, ?)",
        (title, slug, user["id"]),
    )
    page_id = cursor.lastrowid

    # Первая ревизия: автор — черновик, редактор или мастер — сразу утверждённая
    if user["role"] in ("editor", "admin"):
        status = "approved"
    else:
        status = "draft"

    conn.execute(
        """INSERT INTO revisions (page_id, author_id, content, status) VALUES (?, ?, ?, ?)""",
        (page_id, user["id"], content, status),
    )
    conn.commit()
    conn.close()

    flash("Страница создана.")
    return redirect(url_for("page_view", slug=slug))
