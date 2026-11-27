import sqlite3, hashlib, os, hmac
from pathlib import Path
DB = Path(__file__).parent / "data" / "users.sqlite3"

def _conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt BLOB NOT NULL, digest BLOB NOT NULL)")
    return c

def setup_needed():
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

def create_user(username, password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 350000)
    with _conn() as c:
        c.execute("INSERT INTO users VALUES (?, ?, ?)", (username, salt, digest))

def verify_user(username, password):
    with _conn() as c:
        row = c.execute("SELECT salt, digest FROM users WHERE username=?", (username,)).fetchone()
    if not row:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), row[0], 350000)
    return hmac.compare_digest(candidate, row[1])

def logout():
    import streamlit as st
    st.session_state.authenticated = False
    st.session_state.pop("username", None)
