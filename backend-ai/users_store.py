"""Local account storage. The users table lives in the serving database next to the
persistent tables, so pipeline publishes (which only drop forecast tables) never remove it."""

_COLUMNS = ('id', 'email', 'name', 'password_hash', 'role', 'status', 'created_at', 'updated_at', 'last_login_at')


def ensure_users_table(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'worker',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    ''')


def _user(row):
    return dict(zip(_COLUMNS, row)) if row else None


def count_users(conn):
    return int(conn.execute('SELECT COUNT(*) FROM users').fetchone()[0])


def get_user_by_email(conn, email):
    return _user(conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM users WHERE email = ? COLLATE NOCASE",
                              (email.strip().lower(),)).fetchone())


def create_user(conn, *, email, name, password_hash, role, status, now):
    conn.execute('INSERT INTO users (email, name, password_hash, role, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)',
                 (email.strip().lower(), name.strip(), password_hash, role, status, now, now))
    conn.commit()
    return get_user_by_email(conn, email)


def touch_user_login(conn, email, now):
    conn.execute('UPDATE users SET last_login_at = ?, updated_at = ? WHERE email = ? COLLATE NOCASE',
                 (now, now, email.strip().lower()))
    conn.commit()


def list_users(conn):
    columns = [c for c in _COLUMNS if c != 'password_hash']
    rows = conn.execute(f"SELECT {', '.join(columns)} FROM users ORDER BY created_at ASC").fetchall()
    return [dict(zip(columns, row)) for row in rows]


def update_user_role(conn, email, role, now):
    conn.execute('UPDATE users SET role = ?, updated_at = ? WHERE email = ? COLLATE NOCASE',
                 (role, now, email.strip().lower()))
    conn.commit()
    return get_user_by_email(conn, email)
