import os
import sqlite3
from fastapi import FastAPI, Depends, Cookie
from pydantic import BaseModel
import uvicorn
import toml

config = toml.load("server.toml")
addr = config["setting"]["listenAddr"]
port = config["setting"]["listenPort"]
authkey = config["setting"]["authKey"]


def _restful_result(code, status, msg, data):
    return {"code": code, "status": status, "msg": msg, "data": data}


def get_db():
    conn = sqlite3.connect("electricity.db", check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


class Elec(BaseModel):
    timestamp: int
    electricity: float


class Room(BaseModel):
    id: str
    name: str
    table_name: str
    room_group: str


def check_auth(authorization):
    if authorization is None:
        status_code, status, msg = 401, "error", "Need Authorization"
        return _restful_result(status_code, status, msg, "")
    if authorization != authkey:
        status_code, status, msg = 403, "error", "Forbidden"
        return _restful_result(status_code, status, msg, "")


app = FastAPI()


@app.post("/rooms/{room}")
async def add(
    room: str,
    elec: Elec,
    conn: sqlite3.Connection = Depends(get_db),
    Authorization: str = Cookie(default=None),
):
    check_result = check_auth(Authorization)
    if check_result is not None:
        return check_result
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""INSERT INTO {"room_"+room.replace("-","_")} VALUES (?, ?);""",
            (elec.timestamp, elec.electricity),
        )
        conn.commit()
        status_code, status, msg, data = 200, "success", "", ""
    except sqlite3.Error as e:
        status_code, status, msg, data = 500, "error", str(e), ""
    finally:
        cursor.close()
    return _restful_result(status_code, status, msg, data)


@app.post("/rooms")
async def init_room(
    room: Room,
    conn: sqlite3.Connection = Depends(get_db),
    Authorization: str = Cookie(default=None),
):
    check_result = check_auth(Authorization)
    if check_result is not None:
        return check_result
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""REPLACE INTO rooms VALUES (
                           '{room.id}',
                           '{room.name}',
                           '{room.table_name}',
                           '{room.room_group}'  
                           );"""
        )
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {room.table_name}(
                    timestamp INT PRIMARY KEY NOT NULL,
                    electricity INT NOT NULL
                    );"""
        )
        conn.commit()
        status_code, status, msg, data = 200, "success", "", ""
    except sqlite3.Error as e:
        status_code, status, msg, data = 500, "error", str(e), ""
    finally:
        cursor.close()
    return _restful_result(status_code, status, msg, data)


@app.put("/rooms/{room}")
async def update_room(
    room: str,
    room_updated: Room,
    conn: sqlite3.Connection = Depends(get_db),
    Authorization: str | None = Cookie(default=None),
):
    check_result = check_auth(Authorization)
    if check_result is not None:
        return check_result
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""UPDATE rooms SET name = '{room_updated.name}', table_name = '{room_updated.table_name}', room_group = '{room_updated.room_group}' WHERE id = '{room}';"""
        )
        conn.commit()
        status_code, status, msg, data = 200, "success", "", ""
    except sqlite3.Error as e:
        status_code, status, msg, data = 500, "error", str(e), ""
    finally:
        cursor.close()
    return _restful_result(status_code, status, msg, data)


@app.delete("/rooms/{room}")
async def delete_room(
    room: str,
    conn: sqlite3.Connection = Depends(get_db),
    Authorization: str | None = Cookie(default=None),
):
    check_result = check_auth(Authorization)
    if check_result is not None:
        return check_result
    cursor = conn.cursor()
    if room == "rooms":
        status_code, status, msg, data = 403, "error", "Forbidden", ""
        return _restful_result(status_code, status, msg, data)
    try:
        room_table_name = "room_" + room.replace("-", "_")
        cursor.execute(f"""DELETE FROM rooms WHERE id = '{room}';""")
        cursor.execute(f"""DROP TABLE IF EXISTS {room_table_name};""")
        conn.commit()
        status_code, status, msg, data = 200, "success", "", ""
    except sqlite3.Error as e:
        status_code, status, msg, data = 500, "error", str(e), ""
    finally:
        cursor.close()
    return _restful_result(status_code, status, msg, data)


@app.get("/rooms/{room}")
async def query(
    room: str,
    conn: sqlite3.Connection = Depends(get_db),
    Authorization: str | None = Cookie(default=None),
):
    check_result = check_auth(Authorization)
    if check_result is not None:
        return check_result
    cursor = conn.cursor()

    try:
        cursor.execute(f"""SELECT table_name FROM rooms WHERE id = '{room}'""")
        (room_table_name,) = cursor.fetchall()[0]
    except sqlite3.Error as e:
        status_code, status, msg, data = 500, "error", str(e), ""
        cursor.close()
        return _restful_result(status_code, status, msg, data)
    try:
        cursor.execute(f"""SELECT * FROM {room_table_name}""")
        rows = cursor.fetchall()
        cursor.execute(f"PRAGMA table_info({room_table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        status_code, status, msg, data = (
            200,
            "success",
            "",
            {"columns": columns, "data": rows},
        )
    except sqlite3.Error as e:
        status_code, status, msg, data = 500, "error", str(e), ""
    finally:
        cursor.close()
    return _restful_result(status_code, status, msg, data)


@app.get("/rooms")
async def info(
    conn: sqlite3.Connection = Depends(get_db),
    Authorization: str | None = Cookie(default=None),
):
    check_result = check_auth(Authorization)
    if check_result is not None:
        return check_result
    cursor = conn.cursor()
    try:
        cursor.execute(f"""SELECT * FROM rooms""")
        rows = cursor.fetchall()
        cursor.execute(f"""PRAGMA table_info(rooms)""")
        columns = [row[1] for row in cursor.fetchall()]
        status_code, status, msg, data = (
            200,
            "success",
            "",
            {"columns": columns, "data": rows},
        )
    except sqlite3.Error as e:
        status_code, status, msg, data = 500, "error", str(e), ""
    finally:
        cursor.close()
    return _restful_result(status_code, status, msg, data)


@app.delete("/rooms/{room}")
async def delete(
    room: str,
    conn: sqlite3.Connection = Depends(get_db),
    Authorization: str | None = Cookie(default=None),
):
    check_result = check_auth(Authorization)
    if check_result is not None:
        return check_result
    cursor = conn.cursor()
    try:
        room_table_name = "room_" + room.replace("-", "_")
        cursor.execute(f"""DROP TABLE IF EXISTS {room_table_name};);""")
        conn.commit()
        status_code, status, msg, data = 200, "success", "", ""
    except sqlite3.Error as e:
        status_code, status, msg, data = 500, "error", str(e), ""
    finally:
        cursor.close()
    return _restful_result(status_code, status, msg, data)


def init_db():
    conn = sqlite3.connect("electricity.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        f"""CREATE TABLE IF NOT EXISTS rooms(
                    id TEXT PRIMARY KEY NOT NULL,
                    name TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    room_group TEXT NOT NULL
                    );"""
    )
    conn.commit()
    cursor.close()
    conn.close()


if __name__ == "__main__":
    if os.path.exists("electricity.db") is not True:
        init_db()
    uvicorn.run(app, host=addr, port=port)
