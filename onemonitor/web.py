import json
import sys
import httpx
import pandas as pd
import streamlit as st
import toml
from loguru import logger

config = toml.load("web.toml")
page_title = config["setting"]["pageTitle"]
interval = config["setting"]["refreshInterval"]
api_endpoint = config["setting"]["apiEndpoint"]
authkey = config["setting"]["authKey"]

logger.configure(
    handlers=[
        {
            "sink": sys.stderr,
            "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <lvl>{level:^8}</> - <cyan>{name}</cyan> : <cyan>{module}</cyan> : <cyan>{line:^4}</cyan> - <lvl>{message}</>",
            "colorize": True,
        }
    ]
)
logger.add(
    "worker.log",
    rotation="10 MB",
    retention="7 days",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <lvl>{level:^8}</> - <cyan>{name}</cyan> : <cyan>{module}</cyan> : <cyan>{line:^4}</cyan> - <lvl>{message}</>",
)

st.set_page_config(page_title=page_title)


@st.cache_data(ttl=interval)
def fetch_rooms():
    try:
        response = httpx.get(
            f"{api_endpoint}/rooms", cookies={"Authorization": f"{authkey}"}
        )
        logger.info(f"Rooms data refreshed successfully")
        return response
    except Exception as e:
        logger.error(f"An error occurred while refreshing ROOMS data, details: {e}")
        return None


@st.cache_data(ttl=interval)
def fetch_room_electricity(id):
    try:
        response = httpx.get(
            f"{api_endpoint}/rooms/{id}",
            cookies={"Authorization": f"{authkey}"},
        )
        return response
    except Exception as e:
        logger.error(
            f"An error occurred while trying to get data for {name}, details: {e}"
        )
        return None


response = fetch_rooms()

if response:

    id_list = [room[0] for room in json.loads(response.text)["data"]["data"]]
    name_list = [room[1] for room in json.loads(response.text)["data"]["data"]]
    table_name_list = [room[2] for room in json.loads(response.text)["data"]["data"]]
    name2id = dict(zip(name_list, id_list))

    name = st.selectbox("选择房间", name_list)
    response = fetch_room_electricity(name2id[name])
    df = pd.DataFrame(
        json.loads(response.text)["data"]["data"],
        columns=json.loads(response.text)["data"]["columns"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    df.set_index("timestamp", inplace=True)
    # 使用前向填充处理缺失值
    df_hourly = df.resample("h").mean().ffill()
    # 表来！
    st.line_chart(df_hourly["electricity"])
