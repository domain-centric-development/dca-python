import sqlite3  # DCA-LAY-008


def shelf_count(path: str) -> int:
    return len(sqlite3.connect(path).execute("select 1").fetchall())
