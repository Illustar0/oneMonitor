import json
import sys
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
room_id_list = [rooms[i]["id"] for i in range(len(rooms))]
id2room_index = {
    rooms[room_index]["id"]: room_index for room_index in range(len(rooms))
}


# 与云端数据同步
def sync_data_with_cloud():
    logger.info("Synchronize with cloud data")
    try:
        response = httpx.get(
            f"{api_endpoint}/rooms", cookies={"Authorization": f"{authkey}"}
        )
        if response.status_code != 200:
            logger.error(f"Failed to obtain room data from the cloud, API error")
            sys.exit()
        response_json = json.loads(response.text)
        if response_json["code"] != 200:
            logger.error(
                f"Failed to obtain room data from the cloud, API returns: {response_json["msg"]}"
            )
            sys.exit()
    except Exception as e:
        logger.error(f"An error occurred in the GET request, details: {e}")
        sys.exit()
    response_rooms_data = json.loads(response.text)["data"]["data"]
    remote_room_id_list = [
        response_rooms_data[i][0] for i in range(len(response_rooms_data))
    ]
    rooms_should_be_delete = list(set(remote_room_id_list) - set(room_id_list))
    rooms_should_be_add = list(set(room_id_list) - set(remote_room_id_list))
    if rooms_should_be_delete is not None:
        for room_id in rooms_should_be_delete:
            try:
                response = httpx.delete(
                    f"{api_endpoint}/rooms/{room_id}",
                    cookies={"Authorization": f"{authkey}"},
                )
                if response.status_code != 200:
                    logger.error(
                        f"An attempt to delete the room data with id = {room_id} failed, API error"
                    )
                    continue
                response_json = json.loads(response.text)
                if response_json["code"] != 200:
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
    if rooms_should_be_add is not None:
        for room_id in rooms_should_be_add:
            i = id2room_index.get(room_id)
            data = {
                "id": rooms[i]["id"],
                "name": rooms[i]["name"],
                "table_name": "room_" + rooms[i]["id"].replace("-", "_"),
                "description": rooms[i]["description"],
            }
            try:
                response = httpx.post(
                    f"{api_endpoint}/rooms",
                    cookies={"Authorization": f"{authkey}"},
                    json=data,
                )
                if response.status_code != 200:
                    logger.error(
                        f"Failed to initialize room data with id = {room_id}, API error"
                    )
                    continue
                response_json = json.loads(response.text)
                if response_json["code"] != 200:
                    logger.error(
                        f"Failed to initialize room data with id = {room_id}, API returns: {response_json["msg"]}"
                    )
                    continue
                logger.info(f"Successfully initialized room data with id = {room_id}")
            except Exception as e:
                logger.error(f"An error occurred in the POST request, details: {e}")
                continue
    logger.info("Synchronization with cloud data completed")


# 更新电量
def update_electricity(usercode, passwd):
    me = ZZUPy(usercode, passwd)
    me.login()
    for room_id in room_id_list:
        time.sleep(1)
        electricity = me.eCard.get_remaining_power(room_id)
        try:
            response = httpx.post(
                f"{api_endpoint}/rooms/{room_id}",
                cookies={"Authorization": f"{authkey}"},
                json={"timestamp": int(time.time()), "electricity": float(electricity)},
            )
            if response.status_code != 200:
                logger.error(
                    f"Failed to add the electricity record with id = {room_id}, API error"
                )
                continue
            response_json = json.loads(response.text)
            if response_json["code"] != 200:
                logger.error(
                    f"Failed to add the electricity record with id = {room_id}, API returns: {response_json["msg"]}"
                )
                continue
            logger.info(f"Successfully added the power data of room id = {room_id}")
        except Exception as e:
            logger.error(f"An error occurred in the POST request, details: {e}")


if __name__ == "__main__":
    sync_data_with_cloud()
    while True:
        update_electricity(usercode, password)
        logger.info("This cycle ends, waiting to enter the next cycle")
        time.sleep(interval)
