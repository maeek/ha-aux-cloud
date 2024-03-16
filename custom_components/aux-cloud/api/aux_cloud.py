import base64
import hashlib
import json
import aiohttp
import time
from typing import TypedDict

from util import encrypt_aes_cbc_zero_padding


TIMESTAMP_TOKEN_ENCRYPT_KEY = 'kdixkdqp54545^#*'
PASSWORD_ENCRYPT_KEY = '4969fj#k23#'
BODY_ENCRYPT_KEY = 'xgx3d*fe3478$ukx'

AES_INITIAL_VECTOR = bytes([(b + 256) % 256 for b in [-22, -86, -86,
                                                      58, -69, 88, 98, -94, 25, 24, -75, 119, 29, 22, 21, -86]])

LICENSE = 'PAFbJJ3WbvDxH5vvWezXN5BujETtH/iuTtIIW5CE/SeHN7oNKqnEajgljTcL0fBQQWM0XAAAAAAnBhJyhMi7zIQMsUcwR/PEwGA3uB5HLOnr+xRrci+FwHMkUtK7v4yo0ZHa+jPvb6djelPP893k7SagmffZmOkLSOsbNs8CAqsu8HuIDs2mDQAAAAA='
LICENSE_ID = '3c015b249dd66ef0f11f9bef59ecd737'
COMPANY_ID = '48eb1b36cf0202ab2ef07b880ecda60d'

SPOOF_APP_VERSION = "2.2.10.456537160"
SPOOF_USER_AGENT = 'Dalvik/2.1.0 (Linux; U; Android 12; SM-G991B Build/SP1A.210812.016)'
SPOOF_SYSTEM = 'android'
SPOOF_APP_PLATFORM = 'android'

MODELS = {
    "000000000000000000000000c3aa0000": "Heat Pump",
    "000000000000000000000000c0620000": "Air Conditioner",
}

# For some reason this needs to be queried separately
HEAT_PUMP_PARAMS_SPECIAL = [
    'hp_water_tank_temp',
]

# These values are returned by default
HEAT_PUMP_PARAMS = [
    'ver_old',
    'ac_mode',
    'ac_pwr',
    'ac_temp',
    'ecomode',
    'hp_auto_wtemp',
    'hp_fast_hotwater',
    'hp_hotwater_temp',
    'hp_pwr',
    'qtmode'
]


class DirectiveStuData(TypedDict):
  did: str
  devtype: int
  devSession: str


class AuxCloudAPI:
  """
  Class for interacting with AUX cloud services.
  """

  def __init__(self, region: str = 'eu'):
    self.url = "https://app-service-deu-f0e9ebbb.smarthomecs.de" if region == 'eu' else "https://app-service-usa-fd7cc04c.smarthomecs.com"

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
        "loginsession": self.loginsession if hasattr(self, 'loginsession') else '',
        "userid": self.userid if hasattr(self, 'userid') else '',
        **kwargs
    }

  async def login(self, email: str, password: str):
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

      # Token used as an obfuscation attempt, the server validates the token
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
      ) as response:

        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          self.loginsession = json_data['loginsession']
          self.userid = json_data['userid']
        else:
          raise Exception(f"Failed to login: {data}")

        return json_data

  async def list_families(self):
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f'{self.url}/appsync/group/member/getfamilylist',
          headers=self._get_headers(),
      ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          return json_data['data']
        else:
          raise Exception(f"Failed to get families list: {data}")

  async def list_rooms(self, familyid: str):
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f'{self.url}/appsync/group/room/query',
          headers=self._get_headers(familyid=familyid),
      ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          return json_data['data']
        else:
          raise Exception(f"Failed to query a room: {data}")

  async def list_devices(self, familyid: str, shared=False):
    async with aiohttp.ClientSession() as session:
      device_endpoint = 'dev/query?action=select' if not shared else 'sharedev/querylist?querytype=shared'
      async with session.post(
          f'{self.url}/appsync/group/{device_endpoint}',
          data='{"pids":[]}' if not shared else '{"endpointId":""}',
          headers=self._get_headers(familyid=familyid),
      ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          if 'endpoints' in json_data['data']:
            return json_data['data']['endpoints']
          elif 'shareFromOther' in json_data['data']:
            return list(map(lambda dev: dev['devinfo'], json_data['data']['shareFromOther']))
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
      ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if (
            'event' in json_data and
            'payload' in json_data['event'] and
            json_data['event']['payload']['status'] == 0
        ):
          return json_data['event']['payload']
        else:
          raise Exception(f"Failed to query device state: {data}")

  async def query_device_params(self, device: dict, params: list[str] = []):
    """
    Query device parameters. If no parameters are provided, default parameters are queried.
    https://docs-ibroadlink-com.translate.goog/public/configuration-sdk+ctc/message_table/?_x_tr_sl=auto&_x_tr_tl=en&_x_tr_hl=en&_x_tr_pto=wapp
    """

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
                  "act": "get",
                  "params": params,
                  # "prop": "stdctrl",
                  "vals": []
              },
          }
      }

      async with session.post(
          f'{self.url}/device/control/v2/sdkcontrol',
          # Theoretically license in query param is not needed but
          # I'm following the original request made from the app,
          # just in case.
          params={"license": LICENSE},
          data=json.dumps(data, separators=(',', ':')),
          headers=self._get_headers(),
      ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if 'event' in json_data and 'payload' in json_data['event']:
          response = json.loads(
              json_data['event']['payload']['data'])
          response_dict = {}

          for i in range(0, len(response['params'])):
            response_dict[response['params'][i]
                          ] = response['vals'][i][0]['val']

          return response_dict
        else:
          raise Exception(f"Failed to query device state: {data}")
