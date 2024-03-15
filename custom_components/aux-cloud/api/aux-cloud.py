import hashlib
import json
import aiohttp
import asyncio
import time

from util import encrypt_aes_cbc_zero_padding


class AUXCloud:
  """
  Class for interacting with AUX cloud services.
  """

  TIMESTAMP_TOKEN_ENCRYPT_KEY = 'kdixkdqp54545^#*'
  PASSWORD_ENCRYPT_KEY = '4969fj#k23#'
  BODY_ENCRYPT_KEY = 'xgx3d*fe3478$ukx'
  AES_KEY = bytes([(b + 256) % 256 for b in [-22, -86, -86, 58, -69, 88, 98, -94, 25, 24, -75, 119, 29, 22, 21, -86]])

  LICENSE_ID = '3c015b249dd66ef0f11f9bef59ecd737'
  COMPANY_ID ='48eb1b36cf0202ab2ef07b880ecda60d'

  SPOOF_APP_VERSION = "2.2.10.456537160"
  SPOOF_USER_AGENT = 'Dalvik/2.1.0 (Linux; U; Android 12; SM-G991B Build/SP1A.210812.016)'
  SPOOF_SYSTEM = 'android'
  SPOOF_APP_PLATFORM = 'android'

  def __init__(
      self,
      loginsession = None,
      userid = None,
      devices_list = None
    ):
    # European server
    self.url = "https://app-service-deu-f0e9ebbb.smarthomecs.de"
    self.loginsession = loginsession
    self.userid = userid
    self.devices = devices_list


  def _get_headers(self, **kwargs):
    return {
      "Content-Type": "application/x-java-serialized-object",
      "licenseId": AUXCloud.LICENSE_ID,
      "lid": AUXCloud.LICENSE_ID,
      "language": "en",
      "appVersion": AUXCloud.SPOOF_APP_VERSION,
      "User-Agent": AUXCloud.SPOOF_USER_AGENT,
      "system": AUXCloud.SPOOF_SYSTEM,
      "appPlatform": AUXCloud.SPOOF_APP_PLATFORM,
      **kwargs
    }


  async def login(self, email, password):
    async with aiohttp.ClientSession() as session:
      currentTimeInMillis = time.time()
      shaPassword = hashlib.sha1(f'{password}{AUXCloud.PASSWORD_ENCRYPT_KEY}'.encode()).hexdigest()
      payload = {
        "email": email,
        "password": shaPassword,
        "companyid": AUXCloud.COMPANY_ID,
        "lid": AUXCloud.LICENSE_ID
      }
      jsonPayload = json.dumps(payload, separators=(',', ':'))

      # Token used as a obfuscation for the timestamp + secret key
      token = hashlib.md5(f'{jsonPayload}{AUXCloud.BODY_ENCRYPT_KEY}'.encode()).hexdigest()
      
      # Token used for aesNoPadding encryption of stringified json body
      md5 = hashlib.md5(f'{currentTimeInMillis}{AUXCloud.TIMESTAMP_TOKEN_ENCRYPT_KEY}'.encode()).digest()

      async with session.post(
          f'{self.url}/account/login',
          data=encrypt_aes_cbc_zero_padding(AUXCloud.AES_KEY, md5, jsonPayload.encode()),
          headers=self._get_headers(timestamp=f'{currentTimeInMillis}', token=token),
        ) as response:

        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          self.loginsession = json_data['loginsession']
          self.userid = json_data['userid']
        else:
          raise Exception(f"Failed to login: {data}")

        return json_data


  async def query_family(self):
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f'{self.url}/appsync/group/member/getfamilylist',
          headers=self._get_headers(loginsession=self.loginsession, userid=self.userid),
        ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          return json_data['data']
        else:
          raise Exception(f"Failed to get family: {data}")


  async def query_rooms(self, familyid):
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f'{self.url}/appsync/group/room/query',
          headers=self._get_headers(
            loginsession=self.loginsession,
            userid=self.userid,
            familyid=familyid
          ),
        ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          return json_data['data']
        else:
          raise Exception(f"Failed to query a room: {data}")


  async def query_devices(self, familyid):
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f'{self.url}/appsync/group/dev/query?action=select',
          data='{"pids":[]}',
          headers=self._get_headers(
            loginsession=self.loginsession,
            userid=self.userid,
            familyid=familyid
          ),
        ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          return json_data['data']
        else:
          raise Exception(f"Failed to query a room: {data}")


  async def query_shared_devices(self, familyid):
    async with aiohttp.ClientSession() as session:
      async with session.post(
          f'{self.url}/appsync/group/sharedev/querylist?querytype=shared',
          data='{"endpointId":""}',
          headers=self._get_headers(
            loginsession=self.loginsession,
            userid=self.userid,
            familyid=familyid
          ),
        ) as response:
        data = await response.text()
        json_data = json.loads(data)

        if 'status' in json_data and json_data['status'] == 0:
          return json_data['data']
        else:
          raise Exception(f"Failed to query a room: {data}")


  async def query_device_state(self, device_id: str, dev_type: int, dev_session: str):
    async with aiohttp.ClientSession() as session:
      timestamp = int(time.time())
      data = {
        "directive": {
          "header": {
            "namespace": "DNA.QueryState",
            "name": "queryState",
            "interfaceVersion": "2",
            "messageType": "controlgw.batch",
            "senderId": "sdk",
            "messageId": f'{self.userid}-{timestamp}',
            "timstamp": f'{timestamp}'
          },
          "payload": {
            "studata": [
              {
                "did": device_id,
                "devtype": dev_type,
                "devSession": dev_session
              }
            ],
            "msgtype": "batch"
          }
        }
      }


      async with session.post(
          f'{self.url}/device/control/v2/querystate',
          data=json.dumps(data, separators=(',', ':')),
          headers=self._get_headers(
            loginsession=self.loginsession,
            userid=self.userid,
            timestamp=f'{timestamp}'
          ),
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


if __name__ == "__main__":
  # Example usage
  async def main():
    cloud = AUXCloud()
    email = ''
    password = ''
    print(await cloud.login(email, password))
    # print('Family data:')
    # family_data = await cloud.query_family()
    # print(family_data)
    # print('')
    
    # for family in family_data['familyList']:
    #   room_data = await cloud.query_rooms(family['familyid'])
    #   print('Room data:')
    #   print(room_data)
    #   print('')
    #   print('Device data:')
    #   dev_data = await cloud.query_devices(family['familyid'])
    #   print(dev_data)
    #   print('')
    #   print('Shared device data:')
    #   dev_data = await cloud.query_shared_devices(family['familyid'])
    #   print(dev_data)
    #   print('')

    device_data = await cloud.query_device_state('', 25280, '')
    print('Device state:')
    print(device_data)

  loop = asyncio.get_event_loop()
  loop.run_until_complete(main())