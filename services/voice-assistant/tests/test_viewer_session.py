import io,json,os
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from viewer_session import (ViewerSession,ViewerSessionError,NoRedirect,create_session,
    load_credentials,validate_base_url,private_path,child_environment)

TOKEN='a'*40


class Response:
    def __init__(self,data):
        self.raw=data if isinstance(data,bytes) else json.dumps(data).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def getcode(self):return 204 if self.raw==b'' else 200
    def read(self,limit):return self.raw[:limit]


class Opener:
    def __init__(self,*values):self.values=list(values);self.calls=[]
    def open(self,request,timeout):
        self.calls.append(request)
        value=self.values.pop(0)
        if isinstance(value,Exception):raise value
        return Response(value)


class ViewerSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=self.root/'credentials.json'
        self.path.write_text(json.dumps({'schema':'ut.voice.viewer.credentials.v1',
            'purpose':'local_voice_development','email':'voice@test.invalid','password':'test-password-01234567890123456789'}),encoding='utf-8')

    def session(self,opener):
        return create_session(self.path,private_root=self.root,opener=opener)

    def login(self,role='viewer',token=TOKEN):
        return {'accessToken':token,'tokenType':'Bearer','tokenExpiresAt':'2030-01-01T00:00:00+00:00','tokenExpiresIn':899,'user':{'id':7,'role':role}}

    def identity(self,role='viewer',user_id=7):
        return {'id':user_id,'role':role,'email':'voice@test.invalid'}

    def test_loopback_only_and_no_credential_urls(self):
        for value in ['http://host/api','http://192.168.1.1:8000/api','http://localhost:8000/api',
            'http://user:password@127.0.0.1:8000/api','http://127.0.0.1/api',
            'http://127.0.0.1:8000/api?key=abc','http://127.0.0.1:8000/other']:
            with self.subTest(value=value),self.assertRaises(ViewerSessionError):
                validate_base_url(value)
        self.assertEqual(validate_base_url('http://127.0.0.1:8000/api/'),'http://127.0.0.1:8000/api')

    def test_private_directory_escape_rejected(self):
        for path in [self.root,self.root/'not-json.txt',self.root/'../outside.json']:
            with self.subTest(path=str(path)),self.assertRaises(ViewerSessionError):
                private_path(path,self.root)

    def test_oversized_or_malformed_credentials_rejected(self):
        self.path.write_text('x'*65537,encoding='utf-8')
        with self.assertRaises(ViewerSessionError):
            load_credentials(self.path,self.root)

    def test_viewer_login_then_identity_are_the_only_routes(self):
        opener=Opener(self.login(),self.identity())
        session=self.session(opener)
        self.assertEqual([r.full_url for r in opener.calls],
            ['http://127.0.0.1:8000/api/auth/login/','http://127.0.0.1:8000/api/auth/me/'])
        self.assertEqual([r.get_method() for r in opener.calls],['POST','GET'])
        self.assertIsNone(opener.calls[0].get_header('Authorization'))
        self.assertEqual(opener.calls[1].get_header('Authorization'),'Bearer '+TOKEN)
        self.assertNotIn(TOKEN,repr(session))
        self.assertEqual(session.environment()['UT_VOICE_API_TOKEN'],TOKEN)

    def test_administrator_never_passes_login_role_gate(self):
        opener=Opener(self.login('administrator'))
        with self.assertRaises(ViewerSessionError):
            self.session(opener)
        self.assertEqual(len(opener.calls),1)

    def test_role_and_account_identity_must_match(self):
        for identity in [self.identity('operator'),self.identity(user_id=8),
            {**self.identity(),'email':'different@test.invalid'}]:
            with self.subTest(identity=identity),self.assertRaises(ViewerSessionError):
                self.session(Opener(self.login(),identity))

    def test_malformed_token_rejected_before_identity(self):
        opener=Opener(self.login(token='not-a-token'))
        with self.assertRaises(ViewerSessionError):
            self.session(opener)
        self.assertEqual(len(opener.calls),1)

    def test_missing_server_expiry_is_rejected(self):
        login=self.login()
        del login['tokenExpiresAt']
        with self.assertRaises(ViewerSessionError):
            self.session(Opener(login))

    def test_reused_old_token_uses_server_remaining_seconds_despite_clock_skew(self):
        login=self.login()
        login.update(tokenExpiresAt='2000-01-01T00:00:00+00:00',tokenExpiresIn=500)
        session=create_session(self.path,private_root=self.root,opener=Opener(login,self.identity()),clock=lambda:100)
        self.assertEqual(session.valid_until_monotonic,600)
        self.assertFalse(session.needs_refresh(539))
        self.assertTrue(session.needs_refresh(540))

    def test_near_expiry_reused_token_is_revoked_once_then_replaced(self):
        old=self.login();old['tokenExpiresIn']=30
        new=self.login(token='b'*40)
        opener=Opener(old,self.identity(),self.identity(),b'',new,self.identity())
        session=self.session(opener)
        self.assertEqual(session.token,'b'*40)
        self.assertEqual([r.full_url.rsplit('/',2)[1] for r in opener.calls],
            ['login','me','me','logout','login','me'])

    def test_second_short_session_is_not_retried_indefinitely(self):
        old=self.login();old['tokenExpiresIn']=30
        opener=Opener(old,self.identity(),self.identity(),b'',old,self.identity())
        with self.assertRaises(ViewerSessionError):
            self.session(opener)
        self.assertEqual(len(opener.calls),6)

    def test_http_error_and_redirect_do_not_echo_details(self):
        secret='private-error-body'
        opener=Opener(HTTPError('http://127.0.0.1:8000/api/auth/login/',401,secret,{},io.BytesIO(secret.encode())))
        with self.assertRaises(ViewerSessionError) as caught:self.session(opener)
        self.assertNotIn(secret,str(caught.exception))
        with self.assertRaises(ViewerSessionError):NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_oversized_api_response_rejected(self):
        with self.assertRaises(ViewerSessionError):
            self.session(Opener(b'x'*65537))

    def test_child_environment_excludes_cloud_key(self):
        session=ViewerSession('http://127.0.0.1:8000/api',TOKEN,7,'time')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only'},clear=True):
            environment=child_environment(session)
        self.assertNotIn('DEEPSEEK_API_KEY',environment)
        self.assertEqual(environment['UT_VOICE_API_TOKEN'],TOKEN)


if __name__=='__main__':unittest.main()
