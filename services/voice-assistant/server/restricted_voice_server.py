"""Dedicated local voice endpoint. Never starts the upstream OTA or Vision server."""
import argparse,asyncio,copy,hmac,ipaddress,json,logging,os,re,sys,time
from pathlib import Path
from aiohttp import web

MAC=re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',re.I)
UUID=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',re.I)
TOKEN=re.compile(r'[0-9a-f]{64}')
class Denied(Exception):pass

def one(headers,name):
    try:
        if hasattr(headers,'getall'):values=headers.getall(name,[])
        elif hasattr(headers,'get_all'):values=headers.get_all(name)
        else:values=[v for k,v in headers.items() if str(k).lower()==name.lower()]
        if len(values)!=1 or not isinstance(values[0],str):raise Denied()
        return values[0]
    except (KeyError,TypeError,ValueError):raise Denied() from None

class Registry:
    def __init__(self,path):
        p=Path(path)
        if p.stat().st_size>65536:raise ValueError('Registry too large')
        data=json.loads(p.read_text(encoding='utf-8'))
        if set(data)!={'schema','devices'} or data['schema']!='ut.voice.devices.v1':raise ValueError('Invalid registry')
        if not isinstance(data['devices'],list) or not 1<=len(data['devices'])<=16:raise ValueError('Invalid registry')
        self.devices={}
        for item in data['devices']:
            if set(item)!={'device_id','client_id','token'}:raise ValueError('Invalid device')
            mac,client,token=item['device_id'],item['client_id'],item['token']
            if not all(isinstance(v,str) for v in (mac,client,token)):raise ValueError('Invalid device')
            if not MAC.fullmatch(mac) or not UUID.fullmatch(client) or not TOKEN.fullmatch(token):raise ValueError('Invalid device')
            if mac.lower() in self.devices:raise ValueError('Duplicate device')
            self.devices[mac.lower()]=(client.lower(),token)
    def authorize(self,headers):
        mac,client,auth=(one(headers,n) for n in ('Device-Id','Client-Id','Authorization'))
        if not MAC.fullmatch(mac) or not UUID.fullmatch(client) or not auth.startswith('Bearer ') or not TOKEN.fullmatch(auth[7:]):raise Denied()
        entry=self.devices.get(mac.lower())
        correct=hmac.compare_digest(auth[7:],entry[1] if entry else '0'*64)
        if not correct or entry is None or entry[0]!=client.lower():raise Denied()
        return mac.lower(),client.lower()

def validate_host(host,lan=False):
    address=ipaddress.ip_address(host)
    if address.version!=4:raise ValueError('IPv4 literal required')
    if host=='127.0.0.1':
        if lan:raise ValueError('LAN requires a specific private address')
        return host
    networks=('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')
    if not lan or not any(address in ipaddress.ip_network(n) for n in networks):raise ValueError('Explicit private LAN bind required')
    return host

def make_http(registry,ws_url,ready=lambda:True):
    app=web.Application(client_max_size=65536)
    async def health(request):
        return web.json_response({'status':'ready' if ready() else 'starting','restricted':True},status=200 if ready() else 503)
    async def ota(request):
        if request.query_string:raise web.HTTPNotFound()
        try:mac,client=registry.authorize(request.headers)
        except Denied:raise web.HTTPUnauthorized(text='Unauthorized') from None
        try:body=await request.json()
        except web.HTTPRequestEntityTooLarge:raise
        except Exception:raise web.HTTPBadRequest(text='Invalid JSON') from None
        if not isinstance(body,dict) or not isinstance(body.get('application'),dict):raise web.HTTPBadRequest()
        version=body['application'].get('version')
        if not isinstance(version,str) or not re.fullmatch(r'[0-9][A-Za-z0-9.+_-]{0,63}',version):raise web.HTTPBadRequest()
        return web.json_response({'server_time':{'timestamp':int(time.time()*1000),'timezone_offset':480},
            'firmware':{'version':version,'url':''},
            'websocket':{'url':ws_url,'token':registry.devices[mac][1],'version':1}},
            headers={'Cache-Control':'no-store','Pragma':'no-cache'})
    app.router.add_get('/health',health)
    app.router.add_post('/xiaozhi/ota/',ota)
    return app

def restricted_class(Base,Handler,websockets):
    class Restricted(Base):
        def __init__(self,config,registry):
            self.registry=registry;self.active_devices={};self.ready=asyncio.Event()
            super().__init__(config)
        async def _http_response(self,ws,request):
            if request.path!='/xiaozhi/v1/':return ws.respond(404,'Not found\n')
            try:
                self.registry.authorize(request.headers)
                if one(request.headers,'Protocol-Version')!='1':raise Denied()
            except Denied:return ws.respond(401,'Unauthorized\n')
            return None
        async def _handle_connection(self,ws):
            mac=None;reserved=False
            try:
                mac,client=self.registry.authorize(ws.request.headers)
                previous=self.active_devices.get(mac)
                self.active_devices[mac]=ws;reserved=True
                if previous is not None and previous is not ws:
                    await previous.close(code=1001,reason='Authenticated device reconnect')
                for name in ('Authorization','Proxy-Authorization','Cookie','X-Real-IP','X-Forwarded-For','Device-Id','Client-Id'):
                    if name in ws.request.headers:del ws.request.headers[name]
                ws.request.headers['Device-Id']=mac;ws.request.headers['Client-Id']=client
                handler=Handler(self.config,self._vad,self._asr,self._llm,self._memory,self._intent,self)
                await handler.handle_connection(ws)
            except asyncio.CancelledError:raise
            except Exception:self.logger.bind(tag='restricted_admission').error('Device session failed.')
            finally:
                if reserved and self.active_devices.get(mac) is ws:self.active_devices.pop(mac,None)
                await ws.close()
        async def start(self):
            quiet=logging.getLogger('utility_tunnel.restricted.websocket')
            quiet.handlers[:]=[logging.NullHandler()];quiet.propagate=False;quiet.setLevel(logging.CRITICAL)
            bind=self.config['server']
            async with websockets.serve(self._handle_connection,bind['ip'],bind['port'],
                    process_request=self._http_response,ping_interval=None,close_timeout=3,
                    open_timeout=10,compression=None,max_size=65536,max_queue=16,logger=quiet):
                self.ready.set()
                await asyncio.Future()
    return Restricted

def prepare(args,registry):
    root=Path(args.server_root).resolve()
    if not (root/'core/connection.py').is_file():raise ValueError('Pinned server unavailable')
    os.chdir(root);sys.path.insert(0,str(root))
    os.environ['PATH']=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','')
    os.environ.pop('DEEPSEEK_API_KEY',None);os.environ.pop('UT_VOICE_API_TOKEN',None)
    os.environ['UT_VOICE_VIEWER_CREDENTIALS_FILE']=str(Path(args.credentials_file).resolve())
    from config.config_loader import load_config
    config=asyncio.run(load_config())
    expected={'VAD':'SileroVAD','ASR':'SherpaParaformerASR','LLM':'UtilityTunnel','TTS':'BreezeLocal','Memory':'nomem','Intent':'nointent'}
    if any(config.get('selected_module',{}).get(k)!=v for k,v in expected.items()):raise ValueError('Unexpected providers')
    if config.get('read_config_from_api') or config.get('manager-api',{}).get('url') or config.get('mcp_endpoint') or config.get('context_providers') or config.get('voiceprint') or config.get('selected_module',{}).get('VLLM'):raise ValueError('External modules must be disabled')
    if config.get('enable_greeting') is not False or config.get('enable_wakeup_words_response_cache') is not False:raise ValueError('Server greeting must be disabled')
    config['server']['ip']=args.host;config['server']['port']=args.ws_port;config['server']['http_port']=args.http_port
    config['server']['websocket']=f'ws://{args.host}:{args.ws_port}/xiaozhi/v1/'
    from core.utils.cache.manager import cache_manager,CacheType
    cache_manager.set(CacheType.CONFIG,'main_config',config)
    import config.settings as settings
    settings.config_file_valid=True
    from loguru import logger
    secrets=[v[1] for v in registry.devices.values()]+[config['server'].get('auth_key','')]
    def redact(record):
        message=record['message']
        if 'headers:' in message.lower():message='Device request headers omitted.'
        for secret in secrets:
            if len(secret)>=16:message=message.replace(secret,'[redacted]')
        message=re.sub(r'Bearer\s+[A-Za-z0-9._-]+','Bearer [redacted]',message)
        record['message']=message;record['exception']=None
    logger.configure(patcher=redact)
    import config.logger as logs
    logs._logger_initialized=True
    logger.remove()
    logger.add(sys.stdout,format='{time:HH:mm:ss} | {level} | {message}',level='INFO',backtrace=False,diagnose=False)
    from core.websocket_server import WebSocketServer
    from core.connection import ConnectionHandler
    from core.utils.util import check_ffmpeg_installed
    import websockets
    check_ffmpeg_installed()
    return config,restricted_class(WebSocketServer,ConnectionHandler,websockets)

async def run(config,Server,registry,args):
    server=Server(config,registry)
    runner=web.AppRunner(make_http(registry,config['server']['websocket'],server.ready.is_set),access_log=None)
    await runner.setup()
    task=None
    try:
        await web.TCPSite(runner,args.host,args.http_port).start()
        task=asyncio.create_task(server.start())
        await asyncio.wait_for(server.ready.wait(),15)
        print(json.dumps({'state':'ready','restricted':True,'host':args.host,'ws_port':args.ws_port,'http_port':args.http_port,'registered_devices':len(registry.devices),'pid':os.getpid(),'credentials_printed':False}),flush=True)
        await task
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
        await runner.cleanup()

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--server-root',default=r'D:\ut-voice\server')
    parser.add_argument('--registry-file',default=r'D:\ut-voice\private\voice-device.json')
    parser.add_argument('--credentials-file',default=r'D:\ut-voice\private\viewer-credentials.json')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--ws-port',type=int,default=8941)
    parser.add_argument('--http-port',type=int,default=8942)
    parser.add_argument('--lan',action='store_true')
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args(argv)
    try:
        validate_host(args.host,args.lan)
        if not (1024<=args.ws_port<=65535 and 1024<=args.http_port<=65535 and args.ws_port!=args.http_port):raise ValueError('Invalid ports')
        registry=Registry(args.registry_file)
        from viewer_session import load_credentials
        load_credentials(args.credentials_file)
        if args.check_only:
            print(json.dumps({'ready_to_start':True,'registered_devices':len(registry.devices),'host':args.host,'credentials_printed':False}))
            return 0
        config,Server=prepare(args,registry)
        asyncio.run(run(config,Server,registry,args))
        return 0
    except KeyboardInterrupt:return 0
    except Exception as exc:
        print(json.dumps({'state':'failed','error_type':type(exc).__name__,'credentials_printed':False}),flush=True)
        return 2

if __name__=='__main__':raise SystemExit(main())
