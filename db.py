from flask import Flask, render_template,session,request,url_for, redirect,abort,flash  
import sqlite3

app = Flask(__name__)
app.secret_key = "dev-secret"
DB_PATH = "database.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # строки как словари: row["column_name"]
    conn.execute("PRAGMA foreign_keys = ON")  # включить внешние ключи (пригодятся позже)
    return conn

def _migrate_content_to_revisions(conn):
    """
    Один раз: для каждой страницы с контентом создать одну ревизию со статусом approved,
    затем удалить столбец content из pages (через пересоздание таблицы).
    """
    cursor = conn.execute("PRAGMA table_info(pages)")
    columns = [row[1] for row in cursor.fetchall()]
    if "content" not in columns:
        return  # уже мигрировано

    # Заполняем revisions из pages
    conn.execute("""
        INSERT INTO revisions (page_id, author_id, content, status, created_at)
        SELECT id, author_id, content, 'approved', created_at
        FROM pages
    """)

    # В SQLite до 3.35 нет DROP COLUMN — пересоздаём таблицу без content
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("""
        CREATE TABLE pages_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            slug TEXT NOT NULL UNIQUE,
            author_id INTEGER,
            is_locked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            FOREIGN KEY (author_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        INSERT INTO pages_new (id, title, slug, author_id, is_locked, created_at)
        SELECT id, title, slug, author_id, is_locked, created_at FROM pages
    """)
    conn.execute("DROP TABLE pages")
    conn.execute("ALTER TABLE pages_new RENAME TO pages")
    conn.execute("PRAGMA foreign_keys = ON")    

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
            archived_at TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            is_archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL,
            author_id INTEGER,
            content TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK (status IN ('draft', 'pending', 'approved', 'rejected')),
            reviewer_id INTEGER,
            review_note TEXT,
            rollback_reason TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            FOREIGN KEY (page_id) REFERENCES pages(id),
            FOREIGN KEY (author_id) REFERENCES users(id),
            FOREIGN KEY (reviewer_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        column_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        position INTEGER NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
        updated_at TEXT,
        FOREIGN KEY (column_id) REFERENCES columns(id),
        FOREIGN KEY (created_by) REFERENCES users(id)
    )
""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # defaults
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('registration_open', '1')"
    )
    
    _migrate_content_to_revisions(conn)

    conn.commit()
    conn.close()

def insert_test_user():
    """Добавить одного тестового пользователя (для проверки таблицы)."""
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, 'user')",
        ("testuser", "placeholder_hash"),
    )
    conn.commit()
    conn.close()

def show_table():
    """
    Вернуть содержимое таблицы users как список строк.
    Удобно вызывать из консоли: print(show_table()).
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
