import asyncio
import os
import pathlib
from pprint import pprint
import time

import yaml

from custom_components.aux_cloud.api.aux_cloud import LICENSE_ID, AuxCloudAPI


def get_config_path():
    current_dir = pathlib.Path(__file__).parent
    return os.path.join(current_dir, "config.yaml")


if __name__ == "__main__":
    with open(get_config_path(), "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    email: str = config["email"]
    password: str = config["password"]
    shared: bool = config["shared"]

    async def main():
        api = AuxCloudAPI()
        await api.login(email, password)

        async def handle_update(message):
            pprint("Received update:")
            pprint(message)

        await api.initialize_websocket()
        api.ws_api.add_websocket_listener(handle_update)

        # Subscribe to device updates
        await api.ws_api.send_data(
            {
                "data": {
                    "devList": [
                        {
                            "devSession": "xxx",
                            "endpointId": "00000000000000000000xxxxxxxxxxxx",
                            "gatewayId": "",  # Leave empty
                            "pid": "000000000000000000000000c0620000",
                        }
                    ]
                },
                "messageid": time.time(),
                # Subscribe to device updates and fetch the history of the device (last state of parameters)
                # I don't see a diffrence between "subreset" and "sub"
                # "msgtype": "subreset",
                "msgtype": "sub",
                "topic": "devpush",
            }
        )
        """
        Example response:
        {'data': {'data': 'eyJhY19hc3RoZWF0IjowLCJhY19jbGVhbiI6MCwiYWNfaGRpciI6MCwiYWNfaGVhbHRoIjowLCJhY19tYXJrIjoxLCJhY19tb2RlIjowLCJhY19zbHAiOjAsImFjX3RlbXBjb252ZXJ0IjowLCJhY192ZGlyIjowLCJjaGlsZGxvY2siOjAsImNvbWZ3aW5kIjowLCJkaWQiOiIwMDAwMDAwMDAwMDAwMDAwMDAwMFhYWFhYWFhYWFhYWCIsImVjb21vZGUiOjAsIm1sZHByZiI6MCwicGlkIjoiMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwYzA2MjAwMDAiLCJwd3IiOjAsInB3cmxpbWl0IjowLCJwd3JsaW1pdHN3aXRjaCI6MCwic2NyZGlzcCI6MCwic2xlZXBkaXkiOjEsInRlbXAiOjI1MCwidGVtcHVuaXQiOjF9Igo=',
                  'endpointId': '00000000000000000000XXXXXXXXXXXX',
                  'payload': {'change': {'cause': {'msgtype': 48}},
                              'data': '7b2261635f61737468656174223a302c2261635f636c65616e223a302c2261635f68646972223a302c2261635f6865616c7468223a302c2261635f6d61726b223a312c2261635f6d6f6465223a302c2261635f736c70223a302c2261635f74656d70636f6e76657274223a302c2261635f76646972223a302c226368696c646c6f636b223a302c22636f6d6677696e64223a302c22646964223a223030303030303030303030303030303030303030585858585858585858585858222c2265636f6d6f6465223a302c226d6c64707266223a302c22706964223a223030303030303030303030303030303030303030303030306330363230303030222c22707772223a302c227077726c696d6974223a302c227077726c696d6974737769746368223a302c2273637264697370223a302c22736c656570646979223a312c2274656d70223a3235302c2274656d70756e6974223a317d'}},
        'messageid': '1744564848329684206',
        'msgtype': 'push',
        'scope': {},
        'topic': 'devpush'}
        
        Decoded data:
        {"ac_astheat":0,"ac_clean":0,"ac_hdir":0,"ac_health":0,"ac_mark":1,"ac_mode":0,"ac_slp":0,"ac_tempconvert":0,"ac_vdir":0,"childlock":0,"comfwind":0,"did":"00000000000000000000XXXXXXXXXXXX","ecomode":0,"mldprf":0,"pid":"000000000000000000000000c0620000","pwr":0,"pwrlimit":0,"pwrlimitswitch":0,"scrdisp":0,"sleepdiy":1,"temp":250,"tempunit":1}
        """

        # Force query device status and params?
        timestamp = str(int(time.time())) + "000"
        await api.ws_api.send_data(
            {
                "data": {
                    "bodyList": [
                        {
                            "directive": {
                                "endpoint": {
                                    "devicePairedInfo": {
                                        "cookie": "...",
                                        "did": "00000000000000000000XXXXXXXXXXXX",
                                        "mac": "xx:xx:xx:xx:xx:xx",
                                        "pid": "000000000000000000000000c3aa0000",
                                    },
                                    "endpointId": "00000000000000000000XXXXXXXXXXXX",
                                },
                                "header": {
                                    "interfaceVersion": "2",
                                    "messageId": timestamp,
                                    "name": "KeyValueControl",
                                    "namespace": "DNA.KeyValueControl",
                                    "senderId": "sdk",
                                    "timstamp": timestamp,
                                },
                                "payload": {
                                    "act": "get",
                                    "params": [],
                                    "prop": "stdctrl",
                                    "stability": 0,
                                    "vals": [],
                                },
                            }
                        }
                    ],
                    "header": {
                        "familyId": "xxxxxxxxxxxxxx",
                        "language": "en",
                        "licenseid": LICENSE_ID,
                        "loginsession": api.loginsession,
                        "userid": api.userid,
                    },
                },
                "messageid": timestamp,
                "msgtype": "transit.opencontrol",
            }
        )
        """
        Example response:
        {'data': {'responseList': [{'context': {'properties': [{'name': 'vals',
                                                'namespace': 'DNA.KeyValueControl',
                                                'timeOfSample': '2025-04-14_01:59:52.5214Z',
                                                'value': []}]},
                                    'event': {'endpoint': {'endpointId': '00000000000000000000XXXXXXXXXXXX',
                                              'scope': {}},
                                    'header': {'interfaceVersion': '2',
                                              'messageId': '1744567191000',
                                              'name': 'Response',
                                              'namespace': 'DNA.KeyValueControl'},
                                    'payload': {'data': '{"params":["ver_old","ac_mode","ac_pwr","ac_temp","ecomode","hp_auto_wtemp","hp_fast_hotwater","hp_hotwater_temp","hp_pwr","qtmode"], '
                                                '"vals":[[{"val":0,"idx":1}],[{"val":4,"idx":1}],[{"val":0,"idx":1}],[{"val":330,"idx":1}],[{"val":0,"idx":1}],[{"val":9,"idx":1}],[{"val":0,"idx":1}],[{"val":500,"idx":1}],[{"val":1,"idx":1}],[{"val":1,"idx":1}]]}'}}}]},
            'messageid': '1744567191000',
            'msg': 'Success',
            'msgtype': 'transit.opencontrolk',
            'scope': {},
            'status': 0,
            'topic': ''}
        """

        try:
            while True:
                await asyncio.sleep(1)  # Sleep to prevent busy-waiting
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            await api.ws_api.close_websocket()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
