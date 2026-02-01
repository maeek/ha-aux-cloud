import asyncio
import base64
import hashlib
import json
import logging
import time
from typing import TypedDict

import aiohttp

from .const import AuxProducts
from .util import encrypt_aes_cbc_zero_padding
from .aux_cloud_ws import AuxCloudWebSocket

TIMESTAMP_TOKEN_ENCRYPT_KEY = "kdixkdqp54545^#*"
PASSWORD_ENCRYPT_KEY = "4969fj#k23#"
BODY_ENCRYPT_KEY = "xgx3d*fe3478$ukx"

# Body encryption iv
AES_INITIAL_VECTOR = bytes(
    [
        (b + 256) % 256
        for b in [
            -22,
            -86,
            -86,
            58,
            -69,
            88,
            98,
            -94,
            25,
            24,
            -75,
            119,
            29,
            22,
            21,
            -86,
        ]
    ]
)
# pylint: disable=line-too-long
LICENSE = "PAFbJJ3WbvDxH5vvWezXN5BujETtH/iuTtIIW5CE/SeHN7oNKqnEajgljTcL0fBQQWM0XAAAAAAnBhJyhMi7zIQMsUcwR/PEwGA3uB5HLOnr+xRrci+FwHMkUtK7v4yo0ZHa+jPvb6djelPP893k7SagmffZmOkLSOsbNs8CAqsu8HuIDs2mDQAAAAA="
# pylint: enable=line-too-long
LICENSE_ID = "3c015b249dd66ef0f11f9bef59ecd737"
COMPANY_ID = "48eb1b36cf0202ab2ef07b880ecda60d"

SPOOF_APP_VERSION = "2.2.10.456537160"
SPOOF_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 12; SM-G991B Build/SP1A.210812.016)"
SPOOF_SYSTEM = "android"
SPOOF_APP_PLATFORM = "android"

API_SERVER_URL_EU = "https://app-service-deu-f0e9ebbb.smarthomecs.de"
API_SERVER_URL_USA = "https://app-service-usa-fd7cc04c.smarthomecs.com"
API_SERVER_URL_CN = "https://app-service-chn-31a93883.ibroadlink.com"
API_SERVER_URL_RUS = "https://app-service-rus-b8bbc3be.smarthomecs.com"

_LOGGER = logging.getLogger(__package__)


class DirectiveStuData(TypedDict):
    did: str
    devtype: int
    devSession: str


class ExpiredTokenError(Exception):
    pass


class AuxApiError(Exception):
    """Exception raised when querying devices fails."""


class AuxCloudAPI:
    """
    Class for interacting with AUX cloud services.
    """

    def __init__(self, region: str = "eu"):
        self.url = {
            "eu": API_SERVER_URL_EU,
            "usa": API_SERVER_URL_USA,
            "cn": API_SERVER_URL_CN,
            "rus": API_SERVER_URL_RUS,
        }.get(region, API_SERVER_URL_EU)
        self.region = region
        self.families = None
        self.email = None
        self.password = None
        self.loginsession = None
        self.userid = None

        self.ws_api = None

    def _get_headers(self, **kwargs: str):
        return {
            "Content-Type": "application/x-java-serialized-object",
            "licenseId": LICENSE_ID,
            "lid": LICENSE_ID,
            "language": "en",
            "appVersion": SPOOF_APP_VERSION,
            "User-Agent": SPOOF_USER_AGENT,
            "system": SPOOF_SYSTEM,
            "appPlatform": SPOOF_APP_PLATFORM,
            "loginsession": self.loginsession or "",  # Ensure no None values
            "userid": self.userid or "",  # Ensure no None values
            **kwargs,
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: dict = None,
        data: dict = None,
        data_raw: str = None,
        params: dict = None,
        ssl: bool = False,
    ):
        """
        Helper method to make HTTP requests and handle responses.
        """
        url = f"{self.url}/{endpoint}"

        _LOGGER.debug("Making %s request to %s", method, endpoint)
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=url,
                headers=headers,
                data=(
                    data_raw
                    if data_raw
                    else json.dumps(data, separators=(",", ":")) if data else None
                ),
                params=params,
                ssl=ssl,
            ) as response:
                response_text = await response.text()
                try:
                    json_data = json.loads(response_text)
                    return json_data
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Failed to parse JSON response: {response_text}"
                    ) from exc

    async def login(self, email: str = None, password: str = None):
        """
        Login to AUX cloud services.
        """
        email = email if email is not None else self.email
        password = password if password is not None else self.password

        if password is not None:
            self.password = password
        else:
            password = self.password

        current_time = time.time()
        sha_password = hashlib.sha1(
            f"{password}{PASSWORD_ENCRYPT_KEY}".encode()
        ).hexdigest()
        payload = {
            "email": email,
            "password": sha_password,
            "companyid": COMPANY_ID,
            "lid": LICENSE_ID,
        }
        json_payload = json.dumps(payload, separators=(",", ":"))

        # Token used as an obfuscation attempt, the server validates the
        token = hashlib.md5(f"{json_payload}{BODY_ENCRYPT_KEY}".encode()).hexdigest()

        # Token used as key in aes encryption of json body
        md5 = hashlib.md5(
            f"{current_time}{TIMESTAMP_TOKEN_ENCRYPT_KEY}".encode()
        ).digest()

        json_data = await self._make_request(
            method="POST",
            endpoint="account/login",
            headers=self._get_headers(timestamp=f"{current_time}", token=token),
            data_raw=encrypt_aes_cbc_zero_padding(
                AES_INITIAL_VECTOR, md5, json_payload.encode()
            ),
            ssl=False,
        )

        if "status" in json_data and json_data["status"] == 0:
            self.loginsession = json_data["loginsession"]
            self.userid = json_data["userid"]
            _LOGGER.debug("Login successful: %s", self.userid)
            return True

        raise AuxApiError(f"Failed to login: {json_data}")

    def is_logged_in(self):
        """
        Check if the user is logged in.
        """
        # TODO: Implement a request to check if the session is still valid
        return self.loginsession is not None and self.userid is not None

    async def get_families(self):
        """
        List families associated with the user.
        """
        _LOGGER.debug("Getting families list")

        json_data = await self._make_request(
            method="POST",
            endpoint="appsync/group/member/getfamilylist",
            headers=self._get_headers(),
            ssl=False,
        )
        _LOGGER.debug("Families response: %s", json_data)

        if self.families is None:
            self.families = {}

        if "status" in json_data and json_data["status"] == 0:
            for family in json_data["data"]["familyList"]:
                self.families[family["familyid"]] = {
                    "id": family["familyid"],
                    "name": family["name"],
                    "rooms": [],
                    "devices": [],
                }
            return json_data["data"]["familyList"]

        raise AuxApiError(f"Failed to get families list: {json_data}")

    async def get_rooms(self, familyid: str):
        """
        List rooms associated with a family.
        """
        _LOGGER.debug("Getting rooms list for family %s", familyid)
        json_data = await self._make_request(
            method="POST",
            endpoint="appsync/group/room/query",
            headers=self._get_headers(familyid=familyid),
            ssl=False,
        )

        if "status" in json_data and json_data["status"] == 0:
            for room in json_data["data"]["roomList"]:
                self.families[room["familyid"]]["rooms"].append(
                    {"id": room["roomid"], "name": room["name"]}
                )

            return json_data["data"]["roomList"]

        raise AuxApiError(f"Failed to query a room: {json_data}")

    async def get_devices(
        self,
        familyid: str,
        shared=False,
        # List of device endpointIds to fetch from the server
        selected_devices: list[str] = None,
    ):
        """
        List devices associated with a family.
        """
        device_endpoint = (
            "dev/query?action=select"
            if not shared
            else "sharedev/querylist?querytype=shared"
        )
        json_data = await self._make_request(
            method="POST",
            endpoint=f"appsync/group/{device_endpoint}",
            data_raw='{"pids":[]}' if not shared else '{"endpointId":""}',
            headers=self._get_headers(familyid=familyid),
            ssl=False,
        )

        if "status" in json_data and json_data["status"] == 0:
            devices = []

            if "endpoints" in json_data["data"]:
                devices = json_data["data"]["endpoints"] or []
            elif "shareFromOther" in json_data["data"]:
                devices = list(
                    map(lambda dev: dev["devinfo"], json_data["data"]["shareFromOther"])
                )

            # Filter devices if selected_device_ids is provided to fetch only specific devices
            if selected_devices is not None:
                devices = [
                    dev for dev in devices if dev["endpointId"] in selected_devices
                ]

            # Wait for all state tasks to complete
            device_states = await self.bulk_query_device_state(devices)

            # Create tasks for fetching device parameters
            param_tasks = []

            for dev in devices:
                dev["state"] = next(
                    (
                        dev_state["state"]
                        for dev_state in device_states["data"]
                        if dev_state["did"] == dev["endpointId"]
                    ),
                    0,
                )
                # Initialize params as an empty dictionary
                dev["params"] = {}

                _LOGGER.debug(
                    "Device %s is %s - %s",
                    dev["endpointId"],
                    "online" if dev["state"] == 1 else "offline",
                    dev,
                )

                # Create tasks for fetching device params
                dev_params_task = asyncio.create_task(
                    self.get_device_params(dev, params=list([]))
                )
                dev_special_params_task = None

                if AuxProducts.get_special_params_list(dev["productId"]) is not None:
                    dev_special_params_task = asyncio.create_task(
                        self.get_device_params(
                            dev,
                            params=AuxProducts.get_special_params_list(
                                dev["productId"]
                            ),
                        )
                    )

                # Add tasks to the list
                param_tasks.append([dev, dev_params_task, dev_special_params_task])

            # Wait for all tasks to complete
            results = await asyncio.gather(
                *[
                    asyncio.gather(
                        dev_params_task,
                        *(dev_special_params_task,) if dev_special_params_task else (),
                        return_exceptions=True,
                    )
                    for _, dev_params_task, dev_special_params_task in param_tasks
                ],
                return_exceptions=True,
            )

            # Process the results
            for i, (dev, dev_params_task, dev_special_params_task) in enumerate(
                param_tasks
            ):
                dev_params = results[i][0]
                dev_special_params = results[i][1] if len(results[i]) > 1 else None

                if dev_params is None or isinstance(dev_params, BaseException):
                    _LOGGER.error(
                        "Error fetching device params for %s",
                        dev["endpointId"],
                    )
                    continue

                dev["params"] = dev_params or {}

                if dev_special_params and not isinstance(
                    dev_special_params, BaseException
                ):
                    dev["params"].update(dev_special_params)

                dev["last_updated"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime()
                )

            return devices

        raise AuxApiError(f"Failed to query devices: {json_data}")

    def _get_directive_header(
        self, namespace: str, name: str, message_id_prefix: str, **kwargs: str
    ):
        timestamp = int(time.time())
        return {
            "namespace": namespace,
            "name": name,
            "interfaceVersion": "2",
            "senderId": "sdk",
            "messageId": f"{message_id_prefix}-{timestamp}",
            **kwargs,
        }

    async def query_device_state(self, device_id: str, dev_session: str):
        """
        Query device state (On/Off)
        """
        timestamp = int(time.time())
        queried_device = [{"did": device_id, "devSession": dev_session}]
        data = {
            "directive": {
                "header": self._get_directive_header(
                    namespace="DNA.QueryState",
                    name="queryState",
                    # Original header name
                    messageType="controlgw.batch",
                    message_id_prefix=self.userid,
                    # Original header name, probably can be skipped
                    timstamp=f"{timestamp}",
                ),
                "payload": {"studata": queried_device, "msgtype": "batch"},
            }
        }

        json_data = await self._make_request(
            method="POST",
            endpoint="device/control/v2/querystate",
            data=data,
            headers=self._get_headers(),
            ssl=False,
        )

        if (
            "event" in json_data
            and "payload" in json_data["event"]
            and json_data["event"]["payload"]["status"] == 0
        ):
            return json_data["event"]["payload"]

        raise AuxApiError(f"Failed to query device state: {json_data}")

    async def bulk_query_device_state(self, devices: list[dict]):
        """
        Query device state (On/Off)
        """
        timestamp = int(time.time())
        queried_devices = [
            {"did": dev["endpointId"], "devSession": dev["devSession"]}
            for dev in devices
        ]
        data = {
            "directive": {
                "header": self._get_directive_header(
                    namespace="DNA.QueryState",
                    name="queryState",
                    # Original header name
                    messageType="controlgw.batch",
                    message_id_prefix=self.userid,
                    # Original header name, probably can be skipped
                    timstamp=f"{timestamp}",
                ),
                "payload": {"studata": queried_devices, "msgtype": "batch"},
            }
        }

        json_data = await self._make_request(
            method="POST",
            endpoint="device/control/v2/querystate",
            data=data,
            headers=self._get_headers(),
            ssl=False,
        )

        if (
            "event" in json_data
            and "payload" in json_data["event"]
            and json_data["event"]["payload"]["status"] == 0
        ):
            return json_data["event"]["payload"]

        raise AuxApiError(f"Failed to query device state: {json_data}")

    async def _act_device_params(
        self, device: dict, act: str, params: list[str] = None, vals: list[str] = None
    ):
        """
        Query device parameters. If no parameters are provided, default parameters are queried.
        https://docs-ibroadlink-com.translate.goog/public/configuration-sdk+ctc/message_table/?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp
        """
        if params is None:
            params = []
        if vals is None:
            vals = []

        if act == "set" and len(params) != len(vals):
            raise Exception("Params and Vals must have the same length")

        _LOGGER.debug(
            "Acting on device %s with params: %s and vals: %s",
            device["endpointId"],
            params,
            vals,
        )

        cookie = json.loads(base64.b64decode(device["cookie"].encode()))
        mapped_cookie = base64.b64encode(
            json.dumps(
                {
                    "device": {
                        "id": cookie["terminalid"],
                        "key": cookie["aeskey"],
                        "devSession": device["devSession"],
                        "aeskey": cookie["aeskey"],
                        "did": device["endpointId"],
                        "pid": device["productId"],
                        "mac": device["mac"],
                    }
                },
                separators=(",", ":"),
            ).encode()
        ).decode()

        data = {
            "directive": {
                "header": self._get_directive_header(
                    namespace="DNA.KeyValueControl",
                    name="KeyValueControl",
                    message_id_prefix=device["endpointId"],
                ),
                "endpoint": {
                    "devicePairedInfo": {
                        "did": device["endpointId"],
                        "pid": device["productId"],
                        "mac": device["mac"],
                        "devicetypeflag": device["devicetypeFlag"],
                        "cookie": mapped_cookie,
                    },
                    "endpointId": device["endpointId"],
                    "cookie": {},
                    "devSession": device["devSession"],
                },
                "payload": {"act": act, "params": params, "vals": vals},
            }
        }

        data["directive"]["payload"]["did"] = device["endpointId"]

        # Special case for getting ambient mode
        if len(params) == 1 and act == "get":
            data["directive"]["payload"]["vals"] = [[{"val": 0, "idx": 1}]]

        json_data = await self._make_request(
            method="POST",
            endpoint="device/control/v2/sdkcontrol",
            data=data,
            # Theoretically license in query param is not needed but
            # I'm following the original request made from the app,
            # just in case.
            params={"license": LICENSE},
            headers=self._get_headers(),
            ssl=False,
        )

        _LOGGER.debug("Device params response: %s", json_data)

        if (
            "event" in json_data
            and "payload" in json_data["event"]
            and "data" in json_data["event"]["payload"]
            and "header" in json_data["event"]
            and "name" in json_data["event"]["header"]
            # Ensure it's not an error response
            and json_data["event"]["header"]["name"] == "Response"
        ):
            response = json.loads(json_data["event"]["payload"]["data"])
            response_dict = {}

            for i in range(0, len(response["params"])):
                response_dict[response["params"][i]] = response["vals"][i][0]["val"]

            return response_dict

        raise AuxApiError(f"Failed to query device state: {data}, {json_data}")

    async def get_device_params(self, device: dict, params: list[str] = None):
        """
        Query device parameters. If no parameters are provided, default parameters are queried.
        """
        if params is None:
            params = []
        return await self._act_device_params(device, "get", params)

    async def set_device_params(self, device: dict, values: dict):
        """
        Set device parameters
        """
        params = list(values.keys())
        vals = [[{"idx": 1, "val": x}] for x in list(values.values())]
        return await self._act_device_params(device, "set", params, vals)

    async def initialize_websocket(self):
        """
        Initialize the WebSocket connection to receive real-time updates.
        """
        if not self.is_logged_in():
            raise AuxApiError("Cannot initialize WebSocket without being logged in.")

        self.ws_api = AuxCloudWebSocket(
            region=self.region,
            headers=self._get_headers(CompanyId=COMPANY_ID, Origin=self.url),
            loginsession=self.loginsession,
            userid=self.userid,
        )
        await self.ws_api.initialize_websocket()

        timeout = 10  # Timeout in seconds
        start_time = time.time()
        while not self.ws_api.api_initialized:
            if time.time() - start_time > timeout:
                raise TimeoutError("WebSocket API initialization timed out.")

            _LOGGER.debug("Waiting for WebSocket API to initialize...")
            await asyncio.sleep(1)
