import base64
import hashlib
import json
import time
from typing import TypedDict

import aiohttp

from custom_components.aux_cloud.api.const import AUX_MODELS
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
            "loginsession": self.loginsession if hasattr(
                self,
                'loginsession') else '',
            "userid": self.userid if hasattr(
                self,
                'userid') else '',
            **kwargs}

    async def login(self, email: str = None, password: str = None):
        email = email if email is not None else self.email
        password = password if password is not None else self.password

        if password is not None:
            self.password = password
        else:
            password = self.password

        async with aiohttp.ClientSession() as session:
            currentTime = time.time()
            shaPassword = hashlib.sha1(
                f'{password}{PASSWORD_ENCRYPT_KEY}'.encode()).hexdigest()
            payload = {
                "email": email,
                "password": shaPassword,
                "companyid": COMPANY_ID,
                "lid": LICENSE_ID
            }
            jsonPayload = json.dumps(payload, separators=(',', ':'))

            # Token used as an obfuscation attempt, the server validates the
            # token
            token = hashlib.md5(
                f'{jsonPayload}{BODY_ENCRYPT_KEY}'.encode()).hexdigest()

            # Token used as key in aes encryption of json body
            md5 = hashlib.md5(
                f'{currentTime}{TIMESTAMP_TOKEN_ENCRYPT_KEY}'.encode()).digest()

            async with session.post(
                    f'{self.url}/account/login',
                    data=encrypt_aes_cbc_zero_padding(
                        AES_INITIAL_VECTOR, md5, jsonPayload.encode()),
                    headers=self._get_headers(
                        timestamp=f'{currentTime}', token=token),
                    ssl=False
            ) as response:

                data = await response.text()
                json_data = json.loads(data)

                if 'status' in json_data and json_data['status'] == 0:
                    self.loginsession = json_data['loginsession']
                    self.userid = json_data['userid']
                    return True
                else:
                    raise Exception(f"Failed to login: {data}")

    async def list_families(self):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    f'{self.url}/appsync/group/member/getfamilylist',
                    headers=self._get_headers(),
                    ssl=False
            ) as response:
                data = await response.text()
                json_data = json.loads(data)

                if 'status' in json_data and json_data['status'] == 0:
                    self.data = {}
                    for family in json_data['data']['familyList']:
                        self.data[family['familyid']] = {
                            'id': family['familyid'],
                            'name': family['name'],
                            'rooms': [],
                            'devices': []
                        }
                    return json_data['data']['familyList']
                else:
                    raise Exception(f"Failed to get families list: {data}")

    async def list_rooms(self, familyid: str):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    f'{self.url}/appsync/group/room/query',
                    headers=self._get_headers(familyid=familyid),
                    ssl=False
            ) as response:
                data = await response.text()
                json_data = json.loads(data)

                if 'status' in json_data and json_data['status'] == 0:
                    for room in json_data['data']['roomList']:
                        self.data[room['familyid']]['rooms'].append({
                            'id': room['roomid'],
                            'name': room['name']
                        })

                    return json_data['data']['roomList']
                else:
                    raise Exception(f"Failed to query a room: {data}")

    async def list_devices(self, familyid: str, shared=False):
        async with aiohttp.ClientSession() as session:
            device_endpoint = 'dev/query?action=select' if not shared else 'sharedev/querylist?querytype=shared'
            async with session.post(
                    f'{self.url}/appsync/group/{device_endpoint}',
                    data='{"pids":[]}' if not shared else '{"endpointId":""}',
                    headers=self._get_headers(familyid=familyid),
                    ssl=False
            ) as response:

                data = await response.text()
                json_data = json.loads(data)

                if 'status' in json_data and json_data['status'] == 0:
                    devices = []  # Initialize with empty list

                    if 'endpoints' in json_data['data']:
                        devices = json_data['data']['endpoints']
                    elif 'shareFromOther' in json_data['data']:
                        devices = list(
                            map(lambda dev: dev['devinfo'], json_data['data']['shareFromOther']))

                    if devices:
                        for dev in devices:
                            # Check if the device is online
                            dev_state = await self.query_device_state(dev['endpointId'], dev['devSession'])
                            dev['state'] = dev_state['data'][0]['state']

                            # Fetch known params of the device
                            if dev['productId'] in AUX_MODELS and dev['state'] == 1:
                                dev_params = await self.get_device_params(dev, params=list(
                                    AUX_MODELS[dev['productId']]['params'].keys()))
                                dev['params'] = dev_params

                                # Fetch additional params not returned with the
                                # default query
                                if len(AUX_MODELS[dev['productId']]
                                       ['special_params']) != 0:
                                    dev_special_params = await self.get_device_params(dev, params=list(
                                        AUX_MODELS[dev['productId']]['special_params'].keys()))
                                    dev['params'] = {
                                        **dev['params'], **dev_special_params}

                            # Fetch params from unknown device
                            elif dev['state'] == 1:
                                dev_params = await self.get_device_params(dev)
                                dev['params'] = dev_params

                            if not any(d['endpointId'] == dev['endpointId']
                                       for d in self.data[familyid]['devices']):
                                self.data[familyid]['devices'].append(dev)

                    return devices  # Always return devices, even if empty
                else:
                    raise Exception(f"Failed to query a room: {data}")

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
        async with aiohttp.ClientSession() as session:
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

            async with session.post(
                    f'{self.url}/device/control/v2/querystate',
                    data=json.dumps(data, separators=(',', ':')),
                    headers=self._get_headers(),
                    ssl=False
            ) as response:
                data = await response.text()
                json_data = json.loads(data)

                if (
                        'event' in json_data and
                        'payload' in json_data['event'] and
                        json_data['event']['payload']['status'] == 0
                ):
                    return json_data['event']['payload']
                raise Exception(f"Failed to query device state: {data}")

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

        async with aiohttp.ClientSession() as session:
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

            async with session.post(
                    f'{self.url}/device/control/v2/sdkcontrol',
                    # Theoretically license in query param is not needed but
                    # I'm following the original request made from the app,
                    # just in case.
                    params={"license": LICENSE},
                    data=json.dumps(data, separators=(',', ':')),
                    headers=self._get_headers(),
                    ssl=False
            ) as response:
                data = await response.text()
                json_data = json.loads(data)

                if (
                        'event' in json_data and
                        'payload' in json_data['event'] and
                        'data' in json_data['event']['payload']
                ):
                    response = json.loads(
                        json_data['event']['payload']['data'])
                    response_dict = {}

                    for i in range(0, len(response['params'])):
                        response_dict[response['params'][i]
                        ] = response['vals'][i][0]['val']

                    return response_dict
                else:
                    raise Exception(f"Failed to query device state: {data}")

    async def get_device_params(
            self,
            device: dict,
            params: list[str] = []
    ):
        return await self._act_device_params(device, "get", params)

    async def set_device_params(
            self,
            device: dict,
            values: dict
    ):
        params = list(values.keys())
        vals = [[{"idx": 1, "val": x}] for x in list(values.values())]
        return await self._act_device_params(device, "set", params, vals)

    async def refresh(self):
        family_data = await self.list_families()
        for family in family_data:
            await self.list_rooms(family['familyid'])
            await self.list_devices(family['familyid'])
            await self.list_devices(family['familyid'], shared=True)
