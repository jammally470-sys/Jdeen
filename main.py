import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

HERE = Path(__file__).parent
DB_FILE = HERE / "todos.db"  # created automatically on first run


def run(sql, params=()):
    """Run one SQL command and return any rows it produces."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        conn.commit()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def init_db():
    run(
        """CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            position INTEGER NOT NULL
        )"""
    )


@asynccontextmanager
async def lifespan(app):
    init_db()  # create the table when the server starts
    yield


app = FastAPI(lifespan=lifespan)


def all_todos():
    rows = run("SELECT id, text, done, position FROM todos ORDER BY position")
    for r in rows:
        r["done"] = bool(r["done"])
    return rows


class NewTodo(BaseModel):
    text: str


class TodoUpdate(BaseModel):
    text: Optional[str] = None
    done: Optional[bool] = None


class Order(BaseModel):
    ids: list[int]


@app.get("/api/todos")
def list_todos():
    return all_todos()


@app.post("/api/todos")
def add_todo(item: NewTodo):
    text = item.text.strip()
    if not text:
        raise HTTPException(400, "Todo text cannot be empty")
    run(
        "INSERT INTO todos (text, position) "
        "VALUES (?, (SELECT COALESCE(MAX(position), 0) + 1 FROM todos))",
        (text,),
    )
    return all_todos()


@app.put("/api/todos/order")
def reorder(order: Order):
    conn = sqlite3.connect(DB_FILE)
    try:
        for position, todo_id in enumerate(order.ids):
            conn.execute("UPDATE todos SET position = ? WHERE id = ?", (position, todo_id))
        conn.commit()
    finally:
        conn.close()
    return all_todos()


@app.patch("/api/todos/{todo_id}")
def update_todo(todo_id: int, update: TodoUpdate):
    if update.text is not None:
        text = update.text.strip()
        if not text:
            raise HTTPException(400, "Todo text cannot be empty")
        run("UPDATE todos SET text = ? WHERE id = ?", (text, todo_id))
    if update.done is not None:
        run("UPDATE todos SET done = ? WHERE id = ?", (int(update.done), todo_id))
    return all_todos()


@app.delete("/api/todos/{todo_id}")
def delete_todo(todo_id: int):
    run("DELETE FROM todos WHERE id = ?", (todo_id,))
    return all_todos()


@app.get("/")
def home():
    return FileResponse(HERE / "index.html")
