import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
import streamlit as st

DB_PATH = Path("infratwin_local.db")

def _supabase():
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
        if url and key:
            from supabase import create_client
            return create_client(url, key)
    except Exception:
        return None
    return None

def _connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    client = _supabase()
    if client:
        return
    with _connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, role TEXT NOT NULL,
                content TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, modality TEXT NOT NULL,
                result TEXT NOT NULL, created_at TEXT NOT NULL
            )
        """)

def _now():
    return datetime.now(timezone.utc).isoformat()

def create_project(title="New inspection"):
    client = _supabase()
    row = {"id": str(uuid.uuid4()), "title": title, "created_at": _now()}
    if client:
        client.table("projects").insert(row).execute()
    else:
        with _connection() as conn:
            conn.execute(
                "INSERT INTO projects (id, title, created_at) VALUES (?, ?, ?)",
                (row["id"], row["title"], row["created_at"]),
            )
    return row["id"]

def list_projects():
    client = _supabase()
    if client:
        response = client.table("projects").select("*").order("created_at", desc=True).limit(50).execute()
        return response.data or []
    with _connection() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC LIMIT 50").fetchall()
        return [dict(r) for r in rows]

def save_message(project_id, role, content):
    client = _supabase()
    row = {"id": str(uuid.uuid4()), "project_id": project_id, "role": role, "content": content, "created_at": _now()}
    if client:
        client.table("messages").insert(row).execute()
        if role == "user":
            projects = client.table("projects").select("title").eq("id", project_id).limit(1).execute().data or []
            if projects and projects[0]["title"] == "New inspection":
                client.table("projects").update({"title": content.strip().replace("\n", " ")[:40]}).eq("id", project_id).execute()
    else:
        with _connection() as conn:
            conn.execute(
                "INSERT INTO messages (id, project_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (row["id"], row["project_id"], row["role"], row["content"], row["created_at"]),
            )
            if role == "user":
                current = conn.execute("SELECT title FROM projects WHERE id = ?", (project_id,)).fetchone()
                if current and current["title"] == "New inspection":
                    conn.execute("UPDATE projects SET title = ? WHERE id = ?", (content.strip().replace("\n", " ")[:40], project_id))

def get_messages(project_id):
    client = _supabase()
    if client:
        response = client.table("messages").select("role,content").eq("project_id", project_id).order("created_at").execute()
        return response.data or []
    with _connection() as conn:
        rows = conn.execute("SELECT role, content FROM messages WHERE project_id = ? ORDER BY created_at", (project_id,)).fetchall()
        return [dict(r) for r in rows]

def save_inspection(title, modality, result):
    client = _supabase()
    row = {"id": str(uuid.uuid4()), "title": title, "modality": modality, "result": result, "created_at": _now()}
    if client:
        client.table("inspections").insert(row).execute()
    else:
        with _connection() as conn:
            conn.execute(
                "INSERT INTO inspections (id, title, modality, result, created_at) VALUES (?, ?, ?, ?, ?)",
                (row["id"], row["title"], row["modality"], row["result"], row["created_at"]),
            )
    return row["id"]

def list_inspections(limit=100):
    client = _supabase()
    if client:
        response = client.table("inspections").select("*").order("created_at", desc=True).limit(limit).execute()
        return response.data or []
    with _connection() as conn:
        rows = conn.execute("SELECT * FROM inspections ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
