# Copyright © 2025 Illustar0.
# All rights reserved.
import json
import sys
import time
import toml
import httpx
from pushx import Notifier
from zzupy import ZZUPy
from loguru import logger
from http.cookies import SimpleCookie

# 读取配置
config = toml.load("worker.toml")
usercode = config["accounts"]["usercode"]
password = config["accounts"]["password"]
interval = config["setting"]["interval"]
api_endpoint = config["setting"]["apiEndpoint"]
apikey = config["setting"]["apiKey"]
if "cookie" in config["accounts"]:
    cookie = SimpleCookie().load(config["accounts"]["cookie"])
else:
    cookie = None

alarm_line = config["setting"]["alarmLine"]
warning_line = config["setting"]["warningLine"]

pushes = [data for i, data in config["push"].items()]
push_name_list = [pushes[i]["name"] for i in range(len(pushes))]
push_provider_list = [pushes[i]["provider"] for i in range(len(pushes))]
push_params_list = [pushes[i]["params"] for i in range(len(pushes))]
name2provider = dict(zip(push_name_list, push_provider_list))
name2params = dict(zip(push_name_list, push_params_list))

rooms = [data for i, data in config["room"].items()]
room_id_list = [rooms[i]["id"] for i in range(len(rooms))]
id2room_index = {
    rooms[room_index]["id"]: room_index for room_index in range(len(rooms))
}


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
    "worker.log",
    rotation="10 MB",
    retention="7 days",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> - <lvl>{level:^8}</> - <cyan>{name:^12}</cyan> : <cyan>{module:^7}</cyan> : <cyan>{line:^4}</cyan> - <lvl>{message}</>",
)


# 更新房间的信息
def update_room_info(room_id):
    i = id2room_index.get(room_id)
    data = {
        "id": rooms[i]["id"],
        "name": rooms[i]["name"],
        "table_name": "room_" + rooms[i]["id"].replace("-", "_"),
        "room_group": rooms[i]["group"],
    }
    try:
        response = httpx.put(
            f"{api_endpoint}/rooms/{room_id}",
            headers={"Authorization": f"{apikey}"},
            json=data,
        )
        if response.status_code != 200:
            logger.error(
                f"Failed to update room information with id = {room_id}, API error"
            )
        response_json = json.loads(response.text)
        if response_json["status"] != "success":
            logger.error(
                f"Failed to update room information with id = {room_id}, API returns: {response_json['msg']}"
            )
        logger.info(f"Successfully updated room information with id = {room_id}")
    except Exception as e:
        logger.error(f"An error occurred in the PUT request, details: {e}")


# 与云端数据同步
def sync_data_with_cloud():
    logger.info("Synchronize with cloud data")
    try:
        response = httpx.get(
            f"{api_endpoint}/rooms", headers={"Authorization": f"{apikey}"}
        )
        if response.status_code != 200:
            logger.error(f"Failed to obtain room data from the cloud, API error")
            sys.exit()
        response_json = json.loads(response.text)
        if response_json["status"] != "success":
            logger.error(
                f"Failed to obtain room data from the cloud, API returns: {response_json['msg']}"
            )
            sys.exit()
    except Exception as e:
        logger.error(f"An error occurred in the GET request, details: {e}")
        sys.exit()
    response_rooms_data = json.loads(response.text)["data"]
    remote_room_id_list = [
        response_room_data["id"] for response_room_data in response_rooms_data
    ]
    # rooms_should_be_delete = list(set(remote_room_id_list) - set(room_id_list))
    rooms_should_be_add = list(set(room_id_list) - set(remote_room_id_list))
    """
    if rooms_should_be_delete is not None:
        for room_id in rooms_should_be_delete:
            try:
                response = httpx.delete(
                    f"{api_endpoint}/rooms/{room_id}",
                    headers={"Authorization": f"{apikey}"},
                )
                if response.status_code != 200:
                    logger.error(
                        f"An attempt to delete the room data with id = {room_id} failed, API error"
                    )
                    continue
                response_json = json.loads(response.text)
                if response_json["status"] != "success":
                    logger.error(
                        f"An attempt to delete the room data with id = {room_id} failed, API returns: {response_json["msg"]}"
                    )
                    continue
                logger.info(
                    f"Successfully deleted the room related data with id = {room_id}"
                )
            except Exception as e:
                logger.error(f"An error occurred in the DELETE request, details: {e}")
                continue
    """
    if rooms_should_be_add is not None:
        for room_id in rooms_should_be_add:
            i = id2room_index.get(room_id)
            data = {
                "id": rooms[i]["id"],
                "name": rooms[i]["name"],
                "table_name": "room_" + rooms[i]["id"].replace("-", "_"),
                "room_group": rooms[i]["group"],
            }
            try:
                response = httpx.post(
                    f"{api_endpoint}/rooms",
                    headers={"Authorization": f"{apikey}"},
                    json=data,
                )
                if response.status_code != 200:
                    logger.error(
                        f"Failed to initialize room data with id = {room_id}, API error"
                    )
                    continue
                response_json = json.loads(response.text)
                if response_json["status"] != "success":
                    logger.error(
                        f"Failed to initialize room data with id = {room_id}, API returns: {response_json['msg']}"
                    )
                    continue
                logger.info(f"Successfully initialized room data with id = {room_id}")
            except Exception as e:
                logger.error(f"An error occurred in the POST request, details: {e}")
                continue
    for room in rooms:
        # 偷个懒 (
        try:
            response = httpx.get(
                f"{api_endpoint}/rooms", headers={"Authorization": f"{apikey}"}
            )
            if response.status_code != 200:
                logger.error(f"Failed to obtain room data from the cloud, API error")
                sys.exit()
            response_json = json.loads(response.text)
            if response_json["status"] != "success":
                logger.error(
                    f"Failed to obtain room data from the cloud, API returns: {response_json['msg']}"
                )
                sys.exit()
        except Exception as e:
            logger.error(f"An error occurred in the GET request, details: {e}")
            sys.exit()
        response_rooms_data = json.loads(response.text)["data"]
        remote_room_id_list = [
            response_room_data["id"] for response_room_data in response_rooms_data
        ]
        remote_rooms_index = remote_room_id_list.index(room["id"])
        if (
            response_rooms_data[remote_rooms_index]["name"] != room["name"]
            or response_rooms_data[remote_rooms_index]["room_group"] != room["group"]
        ):
            update_room_info(room["id"])
    logger.info("Synchronization with cloud data completed")


# 更新电量 同时 通知
def update_electricity(usercode, passwd, cookie=None):
    me = ZZUPy(usercode, passwd, cookie)
    me.login()
    timestamp = int(time.time())
    for room_id in room_id_list:
        time.sleep(3)
        electricity = me.eCard.get_remaining_power(room_id)
        if "pushName" in rooms[id2room_index[room_id]]:
            if float(electricity) < alarm_line:
                n = Notifier(
                    name2provider[rooms[id2room_index[room_id]]["pushName"]],
                    **name2params[rooms[id2room_index[room_id]]["pushName"]],
                )
                n.notify(
                    title="电费马上要用完啦！！！",
                    content=f"{rooms[id2room_index[room_id]]['name']} 剩余电费：{electricity}",
                )
            elif float(electricity) < warning_line:
                n = Notifier(
                    name2provider[rooms[id2room_index[room_id]]["pushName"]],
                    **name2params[rooms[id2room_index[room_id]]["pushName"]],
                )
                n.notify(
                    title="电费快要用完了",
                    content=f"{rooms[id2room_index[room_id]]['name']} 剩余电费：{electricity}",
                )
        try:
            response = httpx.post(
                f"{api_endpoint}/rooms/{room_id}",
                headers={"Authorization": f"{apikey}"},
                json={"timestamp": timestamp, "electricity": float(electricity)},
            )
            if response.status_code != 200:
                logger.error(
                    f"Failed to add the electricity record with id = {room_id}, API error"
                )
                continue
            response_json = json.loads(response.text)
            if response_json["status"] != "success":
                logger.error(
                    f"Failed to add the electricity record with id = {room_id}, API returns: {response_json['msg']}"
                )
                continue
            logger.info(f"Successfully added the power data of room id = {room_id}")
        except Exception as e:
            logger.error(f"An error occurred in the POST request, details: {e}")


if __name__ == "__main__":
    sync_data_with_cloud()
    while True:
        update_electricity(usercode, password, cookie)
        logger.info("This cycle ends, waiting to enter the next cycle")
        time.sleep(interval)
