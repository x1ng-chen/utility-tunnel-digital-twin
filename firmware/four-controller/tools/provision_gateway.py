"""Local UART provisioning. Opens a port only when --port is explicitly supplied."""
from __future__ import annotations
import argparse,getpass,json,time,uuid
from pathlib import Path

def exchange(port,payload,timeout=8):
    # Import only on execution; pyserial is not needed for inspecting the package.
    import serial
    stream=serial.Serial(baudrate=115200,timeout=.15,write_timeout=2,dsrdtr=False,rtscts=False)
    stream.port=port;stream.dtr=False;stream.rts=False
    with stream:
        stream.write((json.dumps(payload,ensure_ascii=False)+'\n').encode('utf-8'));stream.flush()
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            line=stream.readline(4096)
            try:reply=json.loads(line)
            except (ValueError,UnicodeDecodeError):continue
            if isinstance(reply,dict) and reply.get('schema')=='ut.gateway.config-ack.v1' and reply.get('requestId')==payload['requestId']:
                return reply
    raise RuntimeError('No matching configuration reply; check the port, running image and whether another monitor holds the port.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--action',choices=['set','status','clear'],default='status')
    parser.add_argument('--config-file',type=Path,help='Private JSON; never commit it. Passwords are not accepted as command-line arguments.')
    parser.add_argument('--confirm-clear',action='store_true')
    args=parser.parse_args()
    payload={'schema':'ut.gateway.config.v1','requestId':uuid.uuid4().hex,'action':args.action}
    if args.action=='set':
        fields={'ssid','wifiPassword','mqttHost','mqttPort','mqttUser','mqttPassword','ntpServer'}
        if args.config_file:
            config=json.loads(args.config_file.read_text(encoding='utf-8'))
            if not isinstance(config,dict) or set(config)!=fields:raise ValueError('Configuration requires exactly the seven documented network fields.')
        else:
            config={'ssid':input('Wi-Fi SSID: '),'wifiPassword':getpass.getpass('Wi-Fi password (blank for an open network): '),
                'mqttHost':input('MQTT host LAN address (not 127.0.0.1): '),
                'mqttPort':int(input('MQTT port [1884]: ') or '1884'),'mqttUser':input('MQTT username (optional): '),
                'mqttPassword':getpass.getpass('MQTT password (optional): '),'ntpServer':input('NTP server [pool.ntp.org]: ') or 'pool.ntp.org'}
        payload.update(config)
    elif args.action=='clear':
        if not args.confirm_clear:raise ValueError('Clearing network configuration requires --confirm-clear; the command journal is retained.')
        payload['confirm']='ERASE_NETWORK_CONFIGURATION'
    reply=exchange(args.port,payload)
    # Only fixed acknowledgement fields are printed, never the request/password.
    print(json.dumps(reply,ensure_ascii=False))
    if reply.get('result') not in {'status','saved','unchanged','restarting'}:raise SystemExit(1)
    if reply.get('restart'):print('Configuration saved; gateway is restarting. Query status again. A saved configuration does not prove Wi-Fi/MQTT connectivity.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Library exceptions may include supplied values, so do not dump them.
        raise SystemExit(type(exc).__name__+': configuration failed; verify local input and port. Credentials were not printed.')
