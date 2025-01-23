import json
import time
import toml
import httpx
from zzupy import ZZUPy
from loguru import logger

# 读取配置
config = toml.load("worker.toml")
usercode = config["accounts"]["usercode"]
password = config["accounts"]["password"]
interval = config["setting"]["interval"]
api_endpoint = config["setting"]["apiEndpoint"]
authkey = config["setting"]["authKey"]


rooms = [data for i, data in config["room"].items()]

logger.info("Initialize the room database")

# 初始化 room 的数据库
for i in range(len(rooms)):
    data = {
        "id": rooms[i]["id"],
        "name": rooms[i]["name"],
        "table_name": "room_" + rooms[i]["id"].replace("-", "_"),
        "description": rooms[i]["description"],
    }
    try:
        response = httpx.post(
            f"{api_endpoint}/rooms", cookies={"Authorization": f"{authkey}"}, json=data
        )
        if response.status_code != 200:
            logger.error(f"(id: {rooms[i]["id"]}) Initialization failed, API error")
            continue
        response_json = json.loads(response.text)
        if response_json["code"] != 200:
            logger.error(
                f"{rooms[i]["name"]} Initialization failed, API returns: {response_json["msg"]}"
            )
            continue
        logger.info(f"{rooms[i]["name"]} Initialization success")
    except Exception as e:
        logger.error(f"An error occurred in the POST request, details: {e}")


# 更新电量
def update_electricity(usercode, passwd):
    me = ZZUPy(usercode, passwd)
    me.login()
    for i in range(len(rooms)):
        time.sleep(1)
        electricity = me.eCard.get_remaining_power(rooms[i]["id"])
        try:
            response = httpx.post(
                f"{api_endpoint}/rooms/{rooms[i]["id"]}",
                cookies={"Authorization": f"{authkey}"},
                json={"timestamp": int(time.time()), "electricity": float(electricity)},
            )
            if response.status_code != 200:
                logger.error(
                    f"Failed to add the electricity record of {rooms[i]["name"]}, API error"
                )
                continue
            response_json = json.loads(response.text)
            if response_json["code"] != 200:
                logger.error(
                    f"Failed to add the electricity record of {rooms[i]["name"]}, API returns: {response_json["msg"]}"
                )
                continue
            logger.info(f"Successfully added {rooms[i]["name"]} electricity record")
        except Exception as e:
            logger.error(f"An error occurred in the POST request, details: {e}")


while True:
    update_electricity(usercode, password)
    logger.info("This cycle ends, waiting to enter the next cycle")
    time.sleep(interval)
