from concurrent.futures import ThreadPoolExecutor
import importlib,os
from pathlib import Path
import sys,threading,time,types,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'xiaozhi_adapter'))
from utility_tunnel.client import TunnelVoiceClient,VoiceBridgeError,VoiceReply
from utility_tunnel.viewer_session import ViewerSession
from utility_tunnel.renewing import RenewingTunnelVoiceClient

API='http://127.0.0.1:8000/api'
DIALOGUE=[{'role':'user','content':'你好'}]


class RenewalTests(unittest.TestCase):
    def setup_client(self,actions=None):
        now=[100.0]
        sessions=[]
        calls=[]
        actions=list(actions or [])
        def session_factory(path,base_url):
            time.sleep(.01)
            token=chr(ord('a')+len(sessions))*40
            session=ViewerSession(API,token,7,'received','server-expiry',now[0]+899)
            sessions.append(session)
            return session
        class FakeClient:
            def __init__(self,config):self.config=config
            def ask(self,dialogue):
                calls.append(self.config.token)
                if actions:
                    action=actions.pop(0)
                    if action:raise VoiceBridgeError(action,'safe-test-message')
                return VoiceReply('你好','explanation_only','time')
        client=RenewingTunnelVoiceClient('test-private.json',session_factory=session_factory,
            client_factory=FakeClient,clock=lambda:now[0])
        return client,now,sessions,calls

    def test_valid_session_is_reused_and_refreshed_before_server_expiry(self):
        client,clock,sessions,calls=self.setup_client()
        client.ask(DIALOGUE);client.ask(DIALOGUE)
        self.assertEqual(len(sessions),1)
        clock[0]=940
        client.ask(DIALOGUE)
        self.assertEqual(len(sessions),2)
        self.assertNotEqual(calls[-1],calls[0])

    def test_two_concurrent_queries_only_refresh_once(self):
        client,clock,sessions,calls=self.setup_client()
        client.ask(DIALOGUE)
        clock[0]=940
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:client.ask(DIALOGUE),range(2)))
        self.assertEqual([result.text for result in results],['你好','你好'])
        self.assertEqual(len(sessions),2)
        self.assertEqual(len(calls),3)

    def test_authentication_failure_has_one_refresh_retry(self):
        client,clock,sessions,calls=self.setup_client(['authentication_failed',None])
        self.assertEqual(client.ask(DIALOGUE).text,'你好')
        self.assertEqual(len(sessions),2)
        self.assertEqual(len(calls),2)

    def test_repeated_authentication_failure_stops_after_two_attempts(self):
        client,clock,sessions,calls=self.setup_client(['authentication_failed','authentication_failed'])
        with self.assertRaises(VoiceBridgeError):client.ask(DIALOGUE)
        self.assertEqual(len(sessions),2)
        self.assertEqual(len(calls),2)

    def test_network_or_agent_failure_is_not_replayed(self):
        client,clock,sessions,calls=self.setup_client(['network_error'])
        with self.assertRaises(VoiceBridgeError):client.ask(DIALOGUE)
        self.assertEqual(len(sessions),1)
        self.assertEqual(len(calls),1)


class ProviderModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules={}
        for name in ['core','core.providers','core.providers.llm','core.providers.llm.base']:
            modules[name]=types.ModuleType(name)
        modules['core.providers.llm.base'].LLMProviderBase=object
        with patch.dict(sys.modules,modules):
            cls.provider=importlib.import_module('utility_tunnel.utility_tunnel')

    def test_legacy_explicit_token_contract_remains(self):
        with patch.dict(os.environ,{'UT_VOICE_API_TOKEN':'a'*40},clear=True),patch.object(self.provider,'shared_client') as shared,patch.object(self.provider,'TunnelVoiceClient') as classic:
            provider=self.provider.LLMProvider({})
            self.assertIs(provider.client,classic.return_value)
            self.assertEqual(classic.call_args.args[0].token,'a'*40)
            shared.assert_not_called()

    def test_credentials_file_mode_requires_explicit_opt_in(self):
        with patch.dict(os.environ,{'UT_VOICE_VIEWER_CREDENTIALS_FILE':'private-file.json'},clear=True),patch.object(self.provider,'shared_client') as shared:
            provider=self.provider.LLMProvider({})
            self.assertIs(provider.client,shared.return_value)
            shared.assert_called_once_with('private-file.json',API,65)

    def test_missing_credentials_and_token_still_refuses_startup(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(VoiceBridgeError):
            self.provider.LLMProvider({})


if __name__=='__main__':unittest.main()
