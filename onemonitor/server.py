import json
import os
import sqlite3
from enum import Enum
from typing import List, Any, Dict, Union
from fastapi import FastAPI, Depends, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
import uvicorn
import toml


config = toml.load("server.toml")
addr = config["setting"]["listenAddr"]
port = config["setting"]["listenPort"]
authkey = config["setting"]["authKey"]
auth_key_header = APIKeyHeader(name="Authorization", auto_error=False)


def get_db():
    conn = sqlite3.connect("electricity.db", check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


class AuthKeyException(Exception):
    pass


class StatusEnum(str, Enum):
    success = "success"
    error = "error"
    fail = "fail"


class BaseResponseModel(BaseModel):
    status: StatusEnum = Field(..., description="响应状态，'success'/'error'/'fail'")
    msg: Any = Field(..., description="响应消息，通常为空或包含错误信息")
    data: None = Field(..., description="实际数据")


class SuccessResponseModel(BaseResponseModel):
    status: StatusEnum = Field(default=StatusEnum.success, description="响应状态，成功")


class ErrorResponseModel(BaseResponseModel):
    status: StatusEnum = Field(default=StatusEnum.error, description="响应状态，错误")


class FailResponseModel(BaseResponseModel):
    status: StatusEnum = Field(default=StatusEnum.fail, description="响应状态，失败")


class RoomData(BaseModel):
    id: str = Field(..., description="房间的 ID")
    name: str = Field(..., description="房间的名称")
    table_name: str = Field(..., description="房间对应的数据库表名")
    room_group: str = Field(..., description="房间的组")


class ElectricityData(BaseModel):
    timestamp: int = Field(..., description="时间戳")
    electricity: float = Field(..., description="房间的电量")


class RoomElectricityResponseModel(SuccessResponseModel):
    data: List[ElectricityData] = Field(
        ..., description="实际数据，每组对应一组电力数据"
    )


class InfoResponseModel(SuccessResponseModel):
    data: List[RoomData] = Field(..., description="实际数据，每组对应一个房间")


class ValidationErrorResponseModel(FailResponseModel):
    msg: Dict[str, Union[List[Dict[str, Any]], Any]] = Field(
        ..., description="验证错误的详细信息"
    )


def check_auth_key(auth_key: str = Security(auth_key_header)) -> str:
    if auth_key == authkey:
        return auth_key
    raise AuthKeyException


app = FastAPI()


@app.exception_handler(AuthKeyException)
async def unicorn_exception_handler(request: Request, exc: AuthKeyException):
    response = ErrorResponseModel(
        status=StatusEnum.error, msg="AuthKey is not carried or is incorrect", data=None
    )
    return JSONResponse(
        status_code=401,
        content=json.loads(response.model_dump_json()),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    response = ValidationErrorResponseModel(
        status=StatusEnum.fail,
        msg={"detail": exc.errors(), "body": exc.body},
        data=None,
    )
    return JSONResponse(status_code=422, content=json.loads(response.model_dump_json()))


@app.post(
    "/rooms/{room}",
    responses={
        500: {"model": ErrorResponseModel},
        200: {"model": SuccessResponseModel},
        422: {"model": ValidationErrorResponseModel},
    },
)
async def add(
    room: str,
    electricity: ElectricityData,
    conn: sqlite3.Connection = Depends(get_db),
    auth_key: str = Security(check_auth_key),
):

    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""INSERT INTO {"room_" + room.replace("-", "_")} VALUES (?, ?);""",
            (electricity.timestamp, electricity.electricity),
        )
        conn.commit()
        response = SuccessResponseModel(status=StatusEnum.success, msg="", data=None)
    except sqlite3.Error as e:
        response = ErrorResponseModel(status=StatusEnum.error, msg=str(e), data=None)
        return JSONResponse(json.loads(response.model_dump_json()), 500)
    finally:
        cursor.close()
    return JSONResponse(json.loads(response.model_dump_json()), 200)


@app.post(
    "/rooms",
    responses={
        500: {"model": ErrorResponseModel},
        200: {"model": SuccessResponseModel},
        422: {"model": ValidationErrorResponseModel},
    },
)
async def add_room(
    room: RoomData,
    conn: sqlite3.Connection = Depends(get_db),
    auth_key: str = Security(check_auth_key),
):

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
        response = SuccessResponseModel(status=StatusEnum.success, msg="", data=None)
    except sqlite3.Error as e:
        response = ErrorResponseModel(status=StatusEnum.error, msg=str(e), data=None)
        return JSONResponse(json.loads(response.model_dump_json()), 500)
    finally:
        cursor.close()
    return JSONResponse(json.loads(response.model_dump_json()), 200)


@app.put(
    "/rooms/{room}",
    responses={
        500: {"model": ErrorResponseModel},
        200: {"model": SuccessResponseModel},
        422: {"model": ValidationErrorResponseModel},
    },
)
async def update_room(
    room: str,
    room_updated: RoomData,
    conn: sqlite3.Connection = Depends(get_db),
    auth_key: str = Security(check_auth_key),
):

    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""UPDATE rooms SET name = '{room_updated.name}', table_name = '{room_updated.table_name}', room_group = '{room_updated.room_group}' WHERE id = '{room}';"""
        )
        conn.commit()
        response = SuccessResponseModel(status=StatusEnum.success, msg="", data=None)
    except sqlite3.Error as e:
        response = ErrorResponseModel(status=StatusEnum.error, msg=str(e), data=None)
        return JSONResponse(json.loads(response.model_dump_json()), 500)
    finally:
        cursor.close()
    return JSONResponse(json.loads(response.model_dump_json()), 200)


@app.delete(
    "/rooms/{room}",
    responses={
        500: {"model": ErrorResponseModel},
        200: {"model": SuccessResponseModel},
        422: {"model": ValidationErrorResponseModel},
    },
)
async def delete_room(
    room: str,
    conn: sqlite3.Connection = Depends(get_db),
    auth_key: str = Security(check_auth_key),
):

    cursor = conn.cursor()
    if room == "rooms":
        response = ErrorResponseModel(
            status=StatusEnum.error,
            msg="Cannot delete rooms",
            data=None,
        )
        return JSONResponse(json.loads(response.model_dump_json()), 500)
    try:
        room_table_name = "room_" + room.replace("-", "_")
        cursor.execute(f"""DELETE FROM rooms WHERE id = '{room}';""")
        cursor.execute(f"""DROP TABLE IF EXISTS {room_table_name};""")
        conn.commit()
        response = SuccessResponseModel(status=StatusEnum.success, msg="", data=None)
    except sqlite3.Error as e:
        response = ErrorResponseModel(status=StatusEnum.error, msg=str(e), data=None)
        return JSONResponse(json.loads(response.model_dump_json()), 500)
    finally:
        cursor.close()
    return JSONResponse(json.loads(response.model_dump_json()), 200)


@app.get(
    "/rooms/{room}",
    responses={
        500: {"model": ErrorResponseModel},
        200: {"model": RoomElectricityResponseModel},
        422: {"model": ValidationErrorResponseModel},
    },
)
async def room_electricity(
    room: str,
    conn: sqlite3.Connection = Depends(get_db),
    auth_key: str = Security(check_auth_key),
):
    #
    cursor = conn.cursor()

    try:
        cursor.execute(f"""SELECT table_name FROM rooms WHERE id = '{room}'""")
        (room_table_name,) = cursor.fetchall()[0]
    except sqlite3.Error as e:
        cursor.close()
        response = ErrorResponseModel(status=StatusEnum.error, msg=str(e), data=None)
        return JSONResponse(json.loads(response.model_dump_json()), 500)
    try:
        cursor.execute(f"""SELECT * FROM {room_table_name}""")
        rows = cursor.fetchall()
        response = RoomElectricityResponseModel(
            status=StatusEnum.success,
            msg="",
            data=[
                ElectricityData(timestamp=row[0], electricity=row[1]) for row in rows
            ],
        )
    except sqlite3.Error as e:
        response = ErrorResponseModel(status=StatusEnum.error, msg=str(e), data=None)
        return JSONResponse(json.loads(response.model_dump_json()), 500)
    finally:
        cursor.close()
    return JSONResponse(json.loads(response.model_dump_json()), 200)


@app.get(
    "/rooms",
    responses={
        500: {"model": ErrorResponseModel},
        200: {"model": InfoResponseModel},
        422: {"model": ValidationErrorResponseModel},
    },
)
async def info(
    conn: sqlite3.Connection = Depends(get_db),
    auth_key: str = Security(check_auth_key),
):
    cursor = conn.cursor()
    try:
        cursor.execute(f"""SELECT * FROM rooms""")
        rows = cursor.fetchall()
        response = InfoResponseModel(
            status=StatusEnum(StatusEnum.success),
            msg="",
            data=[
                RoomData(id=row[0], name=row[1], table_name=row[2], room_group=row[3])
                for row in rows
            ],
        )
    except sqlite3.Error as e:
        response = ErrorResponseModel(status=StatusEnum.error, msg=str(e), data=None)
        return JSONResponse(json.loads(response.model_dump_json()), 500)
    finally:
        cursor.close()
    return JSONResponse(json.loads(response.model_dump_json()), 200)


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
