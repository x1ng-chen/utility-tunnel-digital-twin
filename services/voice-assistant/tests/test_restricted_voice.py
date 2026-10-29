import asyncio,importlib.util,json,tempfile,unittest
from types import SimpleNamespace
from pathlib import Path
from multidict import CIMultiDict
from aiohttp.test_utils import TestClient,TestServer
path=Path(__file__).resolve().parents[1]/'server/restricted_voice_server.py'
spec=importlib.util.spec_from_file_location('restricted_voice_under_test',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
MAC='aa:bb:cc:dd:ee:ff';UUID='12345678-1234-4123-8123-123456789012';TOKEN='a'*64
def registry(directory):
 p=Path(directory)/'registry.json'
 p.write_text(json.dumps({'schema':'ut.voice.devices.v1','devices':[{'device_id':MAC,'client_id':UUID,'token':TOKEN}]}),encoding='utf-8')
 return m.Registry(p)
def headers():
 return CIMultiDict({'Device-Id':MAC,'Client-Id':UUID,'Authorization':'Bearer '+TOKEN})
class Policy(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.registry=registry(self.temp.name)
 def test_registered_identity_and_secret_are_all_required(self):
  self.assertEqual(self.registry.authorize(headers()),(MAC,UUID))
  for name in ('Device-Id','Client-Id','Authorization'):
   value=headers();del value[name]
   with self.assertRaises(m.Denied):self.registry.authorize(value)
  for name,value in [('Device-Id','11:22:33:44:55:66'),('Client-Id','87654321-1234-4123-8123-123456789012'),('Authorization','Bearer '+'b'*64)]:
   candidate=headers();candidate[name]=value
   with self.assertRaises(m.Denied):self.registry.authorize(candidate)
 def test_duplicate_credentials_rejected(self):
  for name in ('Device-Id','Client-Id','Authorization'):
   value=headers();value.add(name,value[name])
   with self.assertRaises(m.Denied):self.registry.authorize(value)
 def test_bind_requires_explicit_specific_lan(self):
  self.assertEqual(m.validate_host('127.0.0.1'),'127.0.0.1')
  self.assertEqual(m.validate_host('10.1.2.3',True),'10.1.2.3')
  for host,lan in [('0.0.0.0',True),('8.8.8.8',True),('10.1.2.3',False),('127.0.0.1',True),('localhost',False)]:
   with self.assertRaises(ValueError):m.validate_host(host,lan)
class HttpPolicy(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();self.registry=registry(self.temp.name)
  self.client=TestClient(TestServer(m.make_http(self.registry,'ws://127.0.0.1:8941/xiaozhi/v1/')))
  await self.client.start_server()
 async def asyncTearDown(self):
  await self.client.close();self.temp.cleanup()
 async def test_unauthorized_and_unregistered_paths_cannot_issue_tokens(self):
  for path in ('/mcp/vision/explain','/xiaozhi/ota/?device-id='+MAC):
   response=await self.client.post(path,json={'application':{'version':'1.0.0'}})
   self.assertEqual(response.status,404)
  response=await self.client.post('/xiaozhi/ota/',json={'application':{'version':'1.0.0'}})
  self.assertEqual(response.status,401)
 async def test_ota_returns_same_device_token_and_v1_without_firmware_download(self):
  response=await self.client.post('/xiaozhi/ota/',headers=headers(),json={'application':{'version':'1.0.0'}})
  self.assertEqual(response.status,200)
  data=await response.json()
  self.assertEqual(data['websocket']['token'],TOKEN);self.assertEqual(data['websocket']['version'],1)
  self.assertEqual(data['firmware'],{'version':'1.0.0','url':''})
  self.assertEqual(response.headers['Cache-Control'],'no-store')
 async def test_bad_json_and_oversized_body_rejected(self):
  response=await self.client.post('/xiaozhi/ota/',headers=headers(),json=[])
  self.assertEqual(response.status,400)
  response=await self.client.post('/xiaozhi/ota/',headers=headers(),data=b'x'*65537)
  self.assertEqual(response.status,413)

class Reconnection(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory()
  reg=registry(self.temp.name)
  class Log:
   def bind(self,**kwargs):return self
   def error(self,*args):pass
  class Base:
   def __init__(self,config):
    self.config=config;self._vad=self._asr=self._llm=self._memory=self._intent=None;self.logger=Log()
  class Handler:
   def __init__(self,*args):pass
   async def handle_connection(self,ws):
    self.assert_headers=not ('Authorization' in ws.request.headers)
    ws.handled.set()
    await ws.closed.wait()
  self.server=m.restricted_class(Base,Handler,None)({},reg)
 async def asyncTearDown(self):self.temp.cleanup()
 def connection(self,valid=True):
  class WS:
   def __init__(self):
    self.request=SimpleNamespace(path='/xiaozhi/v1/',headers=headers())
    if not valid:self.request.headers['Authorization']='Bearer '+'b'*64
    self.closed=asyncio.Event();self.handled=asyncio.Event()
   async def close(self,**kwargs):self.closed.set()
  return WS()
 async def test_authenticated_reconnect_replaces_old_socket_without_old_finally_removing_new(self):
  first=self.connection();old=asyncio.create_task(self.server._handle_connection(first))
  await asyncio.wait_for(first.handled.wait(),1)
  second=self.connection();new=asyncio.create_task(self.server._handle_connection(second))
  await asyncio.wait_for(second.handled.wait(),1)
  await asyncio.wait_for(old,1)
  self.assertTrue(first.closed.is_set());self.assertIs(self.server.active_devices[MAC],second)
  self.assertNotIn('Authorization',second.request.headers)
  await second.close();await asyncio.wait_for(new,1)
  self.assertEqual(self.server.active_devices,{})
 async def test_failed_authentication_cannot_evict_active_device(self):
  first=self.connection();old=asyncio.create_task(self.server._handle_connection(first))
  await asyncio.wait_for(first.handled.wait(),1)
  wrong=self.connection(False);await self.server._handle_connection(wrong)
  self.assertIs(self.server.active_devices[MAC],first)
  self.assertFalse(first.closed.is_set());self.assertFalse(wrong.handled.is_set())
  await first.close();await asyncio.wait_for(old,1)

if __name__=='__main__':unittest.main()
