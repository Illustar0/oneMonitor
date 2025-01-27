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
web_auth = config["auth"]["webAuth"]

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

if web_auth:
    from streamlit_authenticator.models import AuthenticationModel
    from streamlit_authenticator.controllers import AuthenticationController
    from streamlit_authenticator.utilities import Validator, Helpers, DeprecationError
    from streamlit_authenticator import RegisterError, LoginError, Authenticate, params

    # 覆写原 streamlit-authenticator 的类以实现对注册页面的自定义
    # Copyright(C)[2024][Mohammad Khorasani]
    class CustomValidator(Validator):
        def validate_password(self, password: str) -> bool:
            pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[~!@#$%^&*()_+])[A-Za-z\d~!@#$%^&*()_+]{8,20}$"
            return bool(re.match(pattern, password))

        def validate_name(self, name: str) -> bool:
            return True

        def validate_email(self, email: str) -> bool:
            return True

    class CustomAuthenticationModel(AuthenticationModel):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        # noinspection PyTypeChecker
        def register_user(
            self,
            new_first_name: str,
            new_last_name: str,
            new_email: str,
            new_username: str,
            new_password: str,
            password_hint: str,
            pre_authorized: Optional[List[str]] = None,
            roles: Optional[List[str]] = None,
            callback: Optional[Callable] = None,
        ) -> tuple:
            if self._credentials_contains_value(new_email):
                raise RegisterError("Email already taken")
            if new_username in self.credentials["usernames"]:
                raise RegisterError("Username/email already taken")
            if not pre_authorized and self.path:
                try:
                    pre_authorized = self.config["pre-authorized"]["emails"]
                except (KeyError, TypeError):
                    pre_authorized = None
            if pre_authorized:
                if new_email in pre_authorized:
                    self._register_credentials(
                        new_username,
                        new_first_name,
                        new_last_name,
                        new_password,
                        new_email,
                        password_hint,
                        roles,
                    )
                    pre_authorized.remove(new_email)
                    if self.path:
                        Helpers.update_config_file(
                            self.path, "pre-authorized", pre_authorized
                        )
                    if callback:
                        callback(
                            {
                                "widget": "Register user",
                                "new_name": new_first_name,
                                "new_last_name": new_last_name,
                                "new_email": new_email,
                                "new_username": new_username,
                            }
                        )
                    return new_email, new_username, f"{new_first_name} {new_last_name}"
                else:
                    raise RegisterError("User not pre-authorized to register")
            self._register_credentials(
                new_username,
                new_first_name,
                new_last_name,
                new_password,
                new_email,
                password_hint,
                roles,
            )
            if callback:
                callback(
                    {
                        "widget": "Register user",
                        "new_name": new_first_name,
                        "new_last_name": new_last_name,
                        "new_email": new_email,
                        "new_username": new_username,
                    }
                )
            return new_email, new_username, f"{new_first_name} {new_last_name}"

    class CustomAuthenticationController(AuthenticationController):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # credentials, auto_hash, path = args[0], args[2], args[3]
            self.authentication_model = CustomAuthenticationModel(
                args[0], args[2], args[3]
            )
            self.validator = CustomValidator()

        # noinspection PyTypeChecker
        def register_user(
            self,
            new_first_name: str,
            new_last_name: str,
            new_email: str,
            new_username: str,
            new_password: str,
            new_password_repeat: str,
            password_hint: str,
            pre_authorized: Optional[List[str]] = None,
            domains: Optional[List[str]] = None,
            roles: Optional[List[str]] = None,
            callback: Optional[Callable] = None,
            captcha: bool = False,
            entered_captcha: Optional[str] = None,
        ) -> tuple:
            new_username = new_username.lower().strip()
            new_password = new_password.strip()
            new_password_repeat = new_password_repeat.strip()
            password_hint = password_hint.strip()
            if not self.validator.validate_username(new_username):
                raise RegisterError("Username is not valid")
            if not self.validator.validate_length(
                new_password, 1
            ) or not self.validator.validate_length(new_password_repeat, 1):
                raise RegisterError("Password/repeat password fields cannot be empty")
            if new_password != new_password_repeat:
                raise RegisterError("Passwords do not match")
            if not self.validator.validate_password(new_password):
                raise RegisterError("Password does not meet criteria")
            if roles and not isinstance(roles, list):
                raise LoginError("Roles must be provided as a list")
            if captcha:
                if not entered_captcha:
                    raise RegisterError("Captcha not entered")
                entered_captcha = entered_captcha.strip()
                self._check_captcha(
                    "register_user_captcha", RegisterError, entered_captcha
                )
            return self.authentication_model.register_user(
                new_first_name,
                new_last_name,
                new_email,
                new_username,
                new_password,
                password_hint,
                pre_authorized,
                roles,
                callback,
            )

    class CustomAuthenticate(Authenticate):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.authentication_controller = AuthenticationController(
                args[0], CustomValidator(), True, self.path
            )

        def register_user(
            self,
            location: str = "main",
            pre_authorized: Optional[List[str]] = None,
            domains: Optional[List[str]] = None,
            fields: Optional[Dict[str, str]] = None,
            captcha: bool = True,
            roles: Optional[List[str]] = None,
            merge_username_email: bool = False,
            clear_on_submit: bool = False,
            key: str = "Register user",
            callback: Optional[Callable] = None,
        ) -> tuple:

            if isinstance(pre_authorized, bool) or isinstance(pre_authorized, dict):
                raise DeprecationError(
                    f"""Please note that the 'pre_authorized' parameter now
                                       requires a list of pre-authorized emails. For further
                                       information please refer to {params.REGISTER_USER_LINK}."""
                )
            if fields is None:
                fields = {
                    "Form name": "Register user",
                    "First name": "First name",
                    "Last name": "Last name",
                    "Email": "Email",
                    "Username": "Username",
                    "Password": "Password",
                    "Repeat password": "Repeat password",
                    "Password hint": "Password hint",
                    "Captcha": "Captcha",
                    "Register": "Register",
                }
            if location not in ["main", "sidebar"]:
                raise ValueError("Location must be one of 'main' or 'sidebar'")
            if location == "main":
                register_user_form = st.form(key=key, clear_on_submit=clear_on_submit)
            elif location == "sidebar":
                register_user_form = st.sidebar.form(
                    key=key, clear_on_submit=clear_on_submit
                )
            else:
                # 消除警告用。
                register_user_form = st.form(key=key, clear_on_submit=clear_on_submit)
            register_user_form.subheader(
                "Register user" if "Form name" not in fields else fields["Form name"]
            )
            # col1_1, col2_1 = register_user_form.columns(2)
            new_username = register_user_form.text_input(
                "Username" if "Username" not in fields else fields["Username"]
            )
            col1_2, col2_2 = register_user_form.columns(2)
            password_instructions = (
                params.PASSWORD_INSTRUCTIONS
                if "password_instructions" not in self.attrs
                else self.attrs["password_instructions"]
            )
            new_password = col1_2.text_input(
                "Password" if "Password" not in fields else fields["Password"],
                type="password",
                help=password_instructions,
            )
            new_password_repeat = col2_2.text_input(
                (
                    "Repeat password"
                    if "Repeat password" not in fields
                    else fields["Repeat password"]
                ),
                type="password",
            )
            password_hint = register_user_form.text_input(
                "Password hint"
                if "Password hint" not in fields
                else fields["Password hint"]
            )
            entered_captcha = None
            if captcha:
                entered_captcha = register_user_form.text_input(
                    "Captcha" if "Captcha" not in fields else fields["Captcha"]
                ).strip()
                register_user_form.image(
                    Helpers.generate_captcha("register_user_captcha")
                )
            if register_user_form.form_submit_button(
                "Register" if "Register" not in fields else fields["Register"]
            ):
                return self.authentication_controller.register_user(
                    "",
                    "",
                    "",
                    new_username,
                    new_password,
                    new_password_repeat,
                    password_hint,
                    pre_authorized if pre_authorized else None,
                    domains,
                    roles,
                    callback,
                    captcha,
                    entered_captcha,
                )
            return None, None, None

    st.set_page_config(page_title=page_title)

    # noinspection PyTypeChecker
    authenticator = CustomAuthenticate(
        config["auth"],
        config["auth"]["cookie"]["name"],
        config["auth"]["cookie"]["key"],
        config["auth"]["cookie"]["expiryDays"],
        # validator=CustomValidator(),
        password_instructions="""
        **Password must be:**
        - Between 8 and 20 characters long.
        - Contain at least one lowercase letter.
        - Contain at least one uppercase letter.
        - Contain at least one digit.
        - Contain at least one special character from [~!@#$%^&*()_+].
        """,
    )


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


if web_auth:

    def on_login_button_click(callback):
        update_config()
        if st.session_state["authentication_status"] is False:
            st.error("Username/password is incorrect")
        elif st.session_state["authentication_status"] is None:
            st.warning("Please enter your username and password")

    def on_logout_button_click(callback):
        update_config()

    def on_register_button_click(callback):
        update_config()


def update_config():
    with open("./web.toml", "w") as file:
        # noinspection PyTypeChecker
        toml.dump(config, file)


placeholder = st.empty()
if web_auth:
    try:
        with placeholder.container():
            if not config["auth"]["usernames"]:
                st.warning("No login information is configured, please register first")
                try:
                    # noinspection PyUnboundLocalVariable
                    (
                        email_of_registered_user,
                        username_of_registered_user,
                        name_of_registered_user,
                    ) = authenticator.register_user(
                        captcha=True, callback=on_register_button_click
                    )
                    if email_of_registered_user:
                        st.success("User registered successfully")
                except Exception as e:
                    st.error(e)
            else:
                # noinspection PyUnboundLocalVariable
                authenticator.login(captcha=True, callback=on_login_button_click)
    except Exception as e:
        st.error(e)


if (
    "authentication_status" in st.session_state
    and st.session_state["authentication_status"] is True
) or web_auth is not True:
    response = fetch_rooms()
    electricity_data = []

    if response:
        id_list = [room["id"] for room in json.loads(response.text)["data"]]
        name_list = [room["name"] for room in json.loads(response.text)["data"]]
        table_name_list = [
            room["table_name"] for room in json.loads(response.text)["data"]
        ]
        group_list = [room["room_group"] for room in json.loads(response.text)["data"]]
        unique_group_list = sorted(list(set(group_list)))
        name2group = dict(zip(name_list, group_list))
        name2id = dict(zip(name_list, id_list))
    else:
        st.error(
            "An error occurred while trying to get data for the rooms, details: {e}"
        )
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

        if electricity_data:
            combined_df = pd.concat(electricity_data)
            st.line_chart(combined_df, y="electricity", color="room")
        else:
            st.write("Please select at least one room to display data 😭")
