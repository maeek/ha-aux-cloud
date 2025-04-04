import base64
import hashlib
import json
import time
from typing import TypedDict
import logging

import aiohttp

from custom_components.aux_cloud.api.const import AUX_MODEL_TO_PARAMS
from custom_components.aux_cloud.api.util import encrypt_aes_cbc_zero_padding

TIMESTAMP_TOKEN_ENCRYPT_KEY = 'kdixkdqp54545^#*'
PASSWORD_ENCRYPT_KEY = '4969fj#k23#'
BODY_ENCRYPT_KEY = 'xgx3d*fe3478$ukx'

# Body encryption iv
AES_INITIAL_VECTOR = bytes([(b + 256) % 256 for b in [-22, -86, -86,
                                                      58, -69, 88, 98, -94, 25, 24, -75, 119, 29, 22, 21, -86]])

LICENSE = 'PAFbJJ3WbvDxH5vvWezXN5BujETtH/iuTtIIW5CE/SeHN7oNKqnEajgljTcL0fBQQWM0XAAAAAAnBhJyhMi7zIQMsUcwR/PEwGA3uB5HLOnr+xRrci+FwHMkUtK7v4yo0ZHa+jPvb6djelPP893k7SagmffZmOkLSOsbNs8CAqsu8HuIDs2mDQAAAAA='
LICENSE_ID = '3c015b249dd66ef0f11f9bef59ecd737'
COMPANY_ID = '48eb1b36cf0202ab2ef07b880ecda60d'

SPOOF_APP_VERSION = "2.2.10.456537160"
SPOOF_USER_AGENT = 'Dalvik/2.1.0 (Linux; U; Android 12; SM-G991B Build/SP1A.210812.016)'
SPOOF_SYSTEM = 'android'
SPOOF_APP_PLATFORM = 'android'

API_SERVER_URL_EU = "https://app-service-deu-f0e9ebbb.smarthomecs.de"
API_SERVER_URL_USA = "https://app-service-usa-fd7cc04c.smarthomecs.com"

_LOGGER = logging.getLogger(__package__)

class DirectiveStuData(TypedDict):
    did: str
    devtype: int
    devSession: str


class ExpiredTokenError(Exception):
    pass


class AuxCloudAPI:
    """
    Class for interacting with AUX cloud services.
    """

    def __init__(self, region: str = 'eu'):
        self.url = API_SERVER_URL_EU if region == 'eu' else API_SERVER_URL_USA
        self.devices = None
        self.families = None
        self.email = None
        self.password = None
        self.loginsession = None
        self.userid = None

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
            "loginsession": self.loginsession or '',  # Ensure no None values
            "userid": self.userid or '',  # Ensure no None values
            **kwargs
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: dict = None,
        data: dict = None,
        data_raw: str = None,
        params: dict = None,
        ssl: bool = False
    ):
        """
        Helper method to make HTTP requests and handle responses.
        """
        url = f"{self.url}/{endpoint}"

        _LOGGER.debug(f"Making {method} request to {endpoint}")
        async with aiohttp.ClientSession() as session:
            async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=data_raw if data_raw else json.dumps(data, separators=(',', ':')) if data else None,
                    params=params,
                    ssl=ssl
            ) as response:
                response_text = await response.text()
                try:
                    json_data = json.loads(response_text)
                    return json_data
                except json.JSONDecodeError:
                    raise Exception(f"Failed to parse JSON response: {response_text}")


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
            f'{password}{PASSWORD_ENCRYPT_KEY}'.encode()).hexdigest()
        payload = {
            "email": email,
            "password": sha_password,
            "companyid": COMPANY_ID,
            "lid": LICENSE_ID
        }
        json_payload = json.dumps(payload, separators=(',', ':'))

        # Token used as an obfuscation attempt, the server validates the
        token = hashlib.md5(
            f'{json_payload}{BODY_ENCRYPT_KEY}'.encode()).hexdigest()

        # Token used as key in aes encryption of json body
        md5 = hashlib.md5(
            f'{current_time}{TIMESTAMP_TOKEN_ENCRYPT_KEY}'.encode()).digest()

        json_data = await self._make_request(
            method='POST',
            endpoint='account/login',
            headers=self._get_headers(timestamp=f'{current_time}', token=token),
            data_raw=encrypt_aes_cbc_zero_padding(AES_INITIAL_VECTOR, md5, json_payload.encode()),
            ssl=False
        )

        if 'status' in json_data and json_data['status'] == 0:
            self.loginsession = json_data['loginsession']
            self.userid = json_data['userid']
            _LOGGER.debug(f"Login successful: {self.userid}")
            return True
        else:
            raise Exception(f"Failed to login: {json_data}")

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
            method='POST',
            endpoint='appsync/group/member/getfamilylist',
            headers=self._get_headers(),
            ssl=False
        )
        _LOGGER.debug(f"Families response: {json_data}")

        if self.families is None:
            self.families = {}

        if 'status' in json_data and json_data['status'] == 0:
            for family in json_data['data']['familyList']:
                self.families[family['familyid']] = {
                    'id': family['familyid'],
                    'name': family['name'],
                    'rooms': [],
                    'devices': []
                }
            return json_data['data']['familyList']
        else:
            raise Exception(f"Failed to get families list: {json_data}")

    async def get_rooms(self, familyid: str):
        """
        List rooms associated with a family.
        """
        _LOGGER.debug(f"Getting rooms list for family {familyid}")
        json_data = await self._make_request(
            method='POST',
            endpoint='appsync/group/room/query',
            headers=self._get_headers(familyid=familyid),
            ssl=False
        )

        if 'status' in json_data and json_data['status'] == 0:
            for room in json_data['data']['roomList']:
                self.families[room['familyid']]['rooms'].append({
                    'id': room['roomid'],
                    'name': room['name']
                })

            return json_data['data']['roomList']
        else:
            raise Exception(f"Failed to query a room: {json_data}")

    async def get_devices(
        self,
        familyid: str,
        shared=False,
        # List of device endpointIds to fetch from the server
        selected_devices: list[str] = None
    ):
        """
        List devices associated with a family.
        """
        device_endpoint = 'dev/query?action=select' if not shared else 'sharedev/querylist?querytype=shared'
        json_data = await self._make_request(
            method='POST',
            endpoint=f'appsync/group/{device_endpoint}',
            data_raw='{"pids":[]}' if not shared else '{"endpointId":""}',
            headers=self._get_headers(familyid=familyid),
            ssl=False
        )

        if 'status' in json_data and json_data['status'] == 0:
            devices = []  # Initialize with empty list

            if 'endpoints' in json_data['data']:
                devices = json_data['data']['endpoints'] or []
            elif 'shareFromOther' in json_data['data']:
                # _LOGGER.info(f"Shared devices found: {json_data['data']}")
                devices = list(
                    map(lambda dev: dev['devinfo'], json_data['data']['shareFromOther']))

            self.devices = []

            # Filter devices if selected_device_ids is provided to fetch only specific devices
            if selected_devices is not None:
                devices = [
                    dev for dev in devices if dev['endpointId'] in selected_devices
                ]

            for dev in devices:
                # Check if the device is online
                dev_state = await self.query_device_state(dev['endpointId'], dev['devSession'])
                dev['state'] = dev_state['data'][0]['state']

                if str(dev['state']) == '1':
                    _LOGGER.debug(f"Device {dev['endpointId']} is online")
                    self.devices.append(dev)

                    dev_params = await self.get_device_params(dev, params=list([]))
                    dev['params'] = dev_params

                    # Fetch known params of the device
                    if dev['productId'] in AUX_MODEL_TO_PARAMS:
                        _LOGGER.debug(f"Fetching special params for device {dev['productId']}: {AUX_MODEL_TO_PARAMS[dev['productId']]}")

                        dev_special_params = await self.get_device_params(dev, params=list(AUX_MODEL_TO_PARAMS[dev['productId']]))

                        if dev is not None and 'params' in dev:
                            _LOGGER.debug(f"Device {dev['endpointId']} has params: {dev['params']}")
                            
                            dev['params'].update(dev_special_params)

                    existing_device = next(
                        (d for d in self.devices if d['endpointId'] == dev['endpointId']), None)
                    if existing_device:
                        # Replace the existing device with the new entry
                        self.devices.remove(existing_device)
            
                    # Add the new device entry
                    dev['last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    self.devices.append(dev)

            return self.devices  # Always return self.devices, even if empty
        else:
            raise Exception(f"Failed to query devices: {json_data}")

    def _get_directive_header(
        self,
        namespace: str,
        name: str,
        message_id_prefix: str,
        **kwargs: str
    ):
        timestamp = int(time.time())
        return {
            "namespace": namespace,
            "name": name,
            "interfaceVersion": "2",
            "senderId": "sdk",
            "messageId": f'{message_id_prefix}-{timestamp}',
            **kwargs
        }

    async def query_device_state(
        self,
        device_id: str,
        dev_session: str
    ):
        """
        Query device state (On/Off)
        """
        timestamp = int(time.time())
        queried_device = [{
            "did": device_id,
            "devSession": dev_session
        }]
        data = {
            "directive": {
                "header": self._get_directive_header(
                    namespace="DNA.QueryState",
                    name="queryState",
                    # Original header name
                    messageType="controlgw.batch",
                    message_id_prefix=self.userid,
                    # Original header name, probably can be skipped
                    timstamp=f'{timestamp}'
                ),
                "payload": {
                    "studata": queried_device,
                    "msgtype": "batch"
                }
            }
        }

        json_data = await self._make_request(
            method='POST',
            endpoint='device/control/v2/querystate',
            data=data,
            headers=self._get_headers(),
            ssl=False
        )

        if (
            'event' in json_data and
            'payload' in json_data['event'] and
            json_data['event']['payload']['status'] == 0
        ):
            return json_data['event']['payload']

        raise Exception(f"Failed to query device state: {json_data}")

    async def _act_device_params(
        self,
        device: dict,
        act: str,
        params: list[str] = [],
        vals: list[str] = []
    ):
        """
        Query device parameters. If no parameters are provided, default parameters are queried.
        https://docs-ibroadlink-com.translate.goog/public/configuration-sdk+ctc/message_table/?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp
        """

        if act == "set" and len(params) != len(vals):
            raise Exception("Params and Vals must have the same length")

        _LOGGER.debug(f"Acting on device {device['endpointId']} with params: {params} and vals: {vals}")

        cookie = json.loads(base64.b64decode(device['cookie'].encode()))
        mapped_cookie = base64.b64encode(json.dumps({
            "device": {
                "id": cookie['terminalid'],
                "key": cookie['aeskey'],
                "devSession": device['devSession'],
                "aeskey": cookie['aeskey'],
                "did": device['endpointId'],
                "pid": device['productId'],
                "mac": device['mac'],
            }
        }, separators=(',', ':')).encode()).decode()

        data = {
            "directive": {
                "header": self._get_directive_header(
                    namespace="DNA.KeyValueControl",
                    name="KeyValueControl",
                    message_id_prefix=device['endpointId']
                ),
                "endpoint": {
                    "devicePairedInfo": {
                        "did": device['endpointId'],
                        "pid": device['productId'],
                        "mac": device['mac'],
                        "devicetypeflag": device['devicetypeFlag'],
                        "cookie": mapped_cookie
                    },
                    "endpointId": device['endpointId'],
                    "cookie": {},
                    "devSession": device['devSession'],
                },
                "payload": {
                    "act": act,
                    "params": params,
                    "vals": vals
                },
            }
        }

        # Special case for getting ambient mode
        if len(params) == 1 and params[0] == 'mode':
            data['directive']['payload']['did'] = device['endpointId']
            data['directive']['payload']['vals'] = [[{'val': 0, 'idx': 1}]]

        json_data = await self._make_request(
            method='POST',
            endpoint='device/control/v2/sdkcontrol',
            data=data,
            # Theoretically license in query param is not needed but
            # I'm following the original request made from the app,
            # just in case.
            params={"license": LICENSE},
            headers=self._get_headers(),
            ssl=False
        )
        
        _LOGGER.debug(f"Device params response: {json_data}")

        if (
                'event' in json_data and
                'payload' in json_data['event'] and
                'data' in json_data['event']['payload']
        ):
            response = json.loads(
                json_data['event']['payload']['data'])
            response_dict = {}

            for i in range(0, len(response['params'])):
                response_dict[response['params'][i]] = response['vals'][i][0]['val']

            return response_dict
        else:
            raise Exception(f"Failed to query device state: {data}")

    async def get_device_params(
            self,
            device: dict,
            params: list[str] = []
    ):
        """
        Query device parameters. If no parameters are provided, default parameters are queried.
        """
        return await self._act_device_params(device, "get", params)

    async def set_device_params(
            self,
            device: dict,
            values: dict
    ):
        """
        Set device parameters
        """
        params = list(values.keys())
        vals = [[{"idx": 1, "val": x}] for x in list(values.values())]
        return await self._act_device_params(device, "set", params, vals)

    async def refresh(self):
        """
        Refresh the device list and family data.
        """
        for family in self.families:
            await self.get_devices(family['familyid'])
            await self.get_devices(family['familyid'], shared=True)

        return True
