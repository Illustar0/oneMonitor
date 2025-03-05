# Copyright © 2025 Illustar0.
# All rights reserved.
import re
import sys
import json
import toml
import httpx
import pandas as pd
import streamlit as st
from loguru import logger
from typing import Optional, List, Callable, Dict

config = toml.load("web.toml")
page_title = config["setting"]["pageTitle"]
interval = config["setting"]["refreshInterval"]
api_endpoint = config["setting"]["apiEndpoint"]
apikey = config["setting"]["apiKey"]

logger.configure(
    handlers=[
        {
            "sink": sys.stderr,
            "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <lvl>{level:^8}</> - <cyan>{name:^12}</cyan> : <cyan>{module:^7}</cyan> : <cyan>{line:^4}</cyan> - <lvl>{message}</>",
            "colorize": True,
        }
    ]
)
logger.add(
    "web.log",
    rotation="10 MB",
    retention="7 days",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <lvl>{level:^8}</> - <cyan>{name:^12}</cyan> : <cyan>{module:^7}</cyan> : <cyan>{line:^4}</cyan> - <lvl>{message}</>",
)


@st.cache_data(ttl=60)
def get_hitokoto():
    try:
        response = httpx.get(f"https://v1.hitokoto.cn")
        logger.info(f"Hitokoto got successfully")
        return response
    except Exception as e:
        logger.error(f"An error occurred while getting hitokoto, details: {e}")
        return None


@st.cache_data(ttl=interval)
def fetch_rooms():
    try:
        response = httpx.get(
            f"{api_endpoint}/rooms", headers={"Authorization": f"{apikey}"}
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
            headers={"Authorization": f"{apikey}"},
        )
        return response
    except Exception as e:
        logger.error(
            f"An error occurred while trying to get data for the room id = {id}, details: {e}"
        )
        return None


def update_config():
    with open("./web.toml", "w") as file:
        # noinspection PyTypeChecker
        toml.dump(config, file)


placeholder = st.empty()

response = fetch_rooms()
electricity_data = []
if response:
    id_list = [room["id"] for room in json.loads(response.text)["data"]]
    name_list = [room["name"] for room in json.loads(response.text)["data"]]
    table_name_list = [room["table_name"] for room in json.loads(response.text)["data"]]
    group_list = [room["room_group"] for room in json.loads(response.text)["data"]]
    unique_group_list = sorted(list(set(group_list)))
    name2group = dict(zip(name_list, group_list))
    name2id = dict(zip(name_list, id_list))
else:
    st.error("An error occurred while trying to get data for the rooms, details: {e}")
    raise ValueError(
        "An error occurred while trying to get data for the rooms, details: {e}"
    )
with st.sidebar:
    st.title("Room list 😘")

    expanders = {}
    for group in unique_group_list:
        expanders[group] = st.expander(group, True)
    for name in name_list:
        # 本来想用 st.page_link 的，多好看，可惜有特性没进版，用不了，哎
        if expanders[name2group[name]].checkbox(label=name):
            response = fetch_room_electricity(name2id[name])
            df = pd.DataFrame(
                json.loads(response.text)["data"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
            df.set_index("timestamp", inplace=True)
            df_hourly = df.resample("h").mean().ffill()
            # 添加房间标识列
            df_hourly["room"] = name
            electricity_data.append(df_hourly[["electricity", "room"]])

    if web_auth:
        # noinspection PyUnboundLocalVariable
        authenticator.logout(callback=on_logout_button_click, location="sidebar")

with placeholder.container():
    st.title("Electricity Data 😎")
    if electricity_data:
        combined_df = pd.concat(electricity_data)
        st.line_chart(combined_df, y="electricity", color="room")
        with st.expander("Hitokoto · 一言"):
            hitokoto_data_json = json.loads(get_hitokoto().text)
            st.write(f"『{hitokoto_data_json['hitokoto']}』")
            st.markdown(
                f"""
                <div style="text-align: right;">
                    ——『{hitokoto_data_json["from"]}』
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.write("Please select at least one room to display data 😭")
