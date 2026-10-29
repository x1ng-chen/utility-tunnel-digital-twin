"""Obtain a short-lived viewer token for the local voice-server process.

This module never starts a service and never prints passwords or tokens.
Credentials and session files belong in the current-user-only private directory.
"""
import argparse
from dataclasses import dataclass,field
from datetime import datetime,timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,ProxyHandler,Request,build_opener

PRIVATE_ROOT=Path(r'D:\ut-voice\private')
DEFAULT_CREDENTIALS=PRIVATE_ROOT/'viewer-credentials.json'
DEFAULT_SESSION=PRIVATE_ROOT/'viewer-session.json'
API_URL='http://127.0.0.1:8000/api'
MAX_BYTES=65536
TOKEN_TTL_SECONDS=900


class ViewerSessionError(Exception):
    def __init__(self,code):
        super().__init__(code)
        self.code=code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ViewerSessionError('redirect_rejected')


def private_path(path,private_root=PRIVATE_ROOT):
    try:
        root=Path(private_root).resolve(strict=True)
        result=Path(path).resolve()
        result.relative_to(root)
        if result==root or result.suffix.lower()!='.json':
            raise ValueError
        return result
    except (OSError,ValueError):
        raise ViewerSessionError('private_path_required') from None


def validate_base_url(value):
    try:
        parsed=urlsplit(value)
        if (parsed.scheme not in {'http','https'} or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path.rstrip('/')!='/api'
                or not parsed.port or any(c.isspace() for c in value)
                or not ipaddress.ip_address(parsed.hostname).is_loopback):
            raise ValueError
        return value.rstrip('/')
    except (TypeError,ValueError):
        raise ViewerSessionError('numeric_loopback_api_required') from None


def load_credentials(path=DEFAULT_CREDENTIALS,private_root=PRIVATE_ROOT):
    path=private_path(path,private_root)
    try:
        if path.stat().st_size>MAX_BYTES:
            raise ValueError
        data=json.loads(path.read_text(encoding='utf-8'))
        email=data['email']
        password=data['password']
        if (data.get('schema')!='ut.voice.viewer.credentials.v1'
                or data.get('purpose')!='local_voice_development'
                or not isinstance(email,str) or not email.isascii()
                or not 3<=len(email)<=254 or '@' not in email or any(c.isspace() for c in email)
                or not isinstance(password,str) or not password.isascii()
                or not 24<=len(password)<=256 or any(c.isspace() for c in password)):
            raise ValueError
        return {'email':email.strip().lower(),'password':password}
    except (OSError,ValueError,KeyError,TypeError):
        raise ViewerSessionError('private_credentials_invalid') from None


@dataclass(frozen=True)
class ViewerSession:
    base_url:str
    token:str=field(repr=False)
    user_id:int=0
    obtained_at_utc:str=''
    expires_at_utc:str=''
    valid_until_monotonic:float=field(default=0.0,repr=False)

    def environment(self):
        return {'UT_VOICE_API_URL':self.base_url,'UT_VOICE_API_TOKEN':self.token}

    def needs_refresh(self,now=None,window=60):
        return self.valid_until_monotonic-(time.monotonic() if now is None else now)<=window


def _request(opener,url,payload=None,token=None):
    body=None if payload is None else json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')
    headers={'Accept':'application/json','Content-Type':'application/json'}
    if token is not None:
        headers['Authorization']='Bearer '+token
    request=Request(url,data=body,headers=headers,method='POST' if body is not None else 'GET')
    try:
        with opener.open(request,timeout=10) as response:
            if response.getcode()!=200:
                raise ViewerSessionError('api_status_rejected')
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise ViewerSessionError('api_response_too_large')
        result=json.loads(raw)
        if not isinstance(result,dict):
            raise ValueError
        return result
    except HTTPError as exc:
        raise ViewerSessionError('login_or_identity_rejected' if exc.code in {401,403} else 'api_unavailable') from None
    except (URLError,TimeoutError,OSError):
        raise ViewerSessionError('api_unreachable') from None
    except (ValueError,TypeError,UnicodeError):
        raise ViewerSessionError('api_response_invalid') from None


def _login_verified(credentials,base_url,opener,clock):
    began=clock()
    login=_request(opener,base_url+'/auth/login/',credentials)
    user=login.get('user')
    token=login.get('accessToken')
    if (not isinstance(user,dict) or user.get('role')!='viewer'
            or not isinstance(token,str) or not re.fullmatch(r'[a-fA-F0-9]{40}',token)
            or login.get('tokenType')!='Bearer'):
        raise ViewerSessionError('viewer_login_required')
    try:
        expires_at=datetime.fromisoformat(login['tokenExpiresAt'].replace('Z','+00:00'))
        remaining=login['tokenExpiresIn']
        if expires_at.tzinfo is None or isinstance(remaining,bool) or not isinstance(remaining,int) or not 0<remaining<=TOKEN_TTL_SECONDS:
            raise ValueError
    except (KeyError,ValueError,TypeError,AttributeError):
        raise ViewerSessionError('server_expiry_metadata_required') from None
    identity=_request(opener,base_url+'/auth/me/',token=token)
    user_id=identity.get('id')
    if (identity.get('role')!='viewer' or isinstance(user_id,bool) or not isinstance(user_id,int)
            or user_id<=0 or user_id!=user.get('id')
            or identity.get('email','').lower()!=credentials['email']):
        raise ViewerSessionError('viewer_identity_mismatch')
    return ViewerSession(base_url,token,user_id,datetime.now(timezone.utc).isoformat(),
        expires_at.astimezone(timezone.utc).isoformat(),began+remaining)


def _revoke_own_viewer(session,opener):
    identity=_request(opener,session.base_url+'/auth/me/',token=session.token)
    if identity.get('role')!='viewer' or identity.get('id')!=session.user_id:
        raise ViewerSessionError('viewer_identity_mismatch')
    request=Request(session.base_url+'/auth/logout/',data=b'{}',
        headers={'Accept':'application/json','Content-Type':'application/json',
                 'Authorization':'Bearer '+session.token},method='POST')
    try:
        with opener.open(request,timeout=10) as response:
            if response.getcode()!=204:
                raise ViewerSessionError('viewer_session_revoke_failed')
            response.read(1)
    except HTTPError as exc:
        if exc.code!=401:
            raise ViewerSessionError('viewer_session_revoke_failed') from None
    except (URLError,OSError,TimeoutError):
        raise ViewerSessionError('api_unreachable') from None


def create_session(credentials_path=DEFAULT_CREDENTIALS,base_url=API_URL,private_root=PRIVATE_ROOT,opener=None,clock=time.monotonic):
    base_url=validate_base_url(base_url)
    credentials=load_credentials(credentials_path,private_root)
    opener=opener if opener is not None else build_opener(ProxyHandler({}),NoRedirect())
    session=_login_verified(credentials,base_url,opener,clock)
    if session.needs_refresh(clock()):
        # Only this already verified dedicated viewer token is revoked.
        # The server may otherwise reuse a still-valid token when its own renewal window is smaller.
        _revoke_own_viewer(session,opener)
        session=_login_verified(credentials,base_url,opener,clock)
        if session.needs_refresh(clock()):
            raise ViewerSessionError('fresh_viewer_session_too_short')
    return session


def persist_session(session,path=DEFAULT_SESSION,private_root=PRIVATE_ROOT):
    path=private_path(path,private_root)
    data={'schema':'ut.voice.viewer.session.v1','base_url':session.base_url,'token':session.token,
          'role':'viewer','user_id':session.user_id,'obtained_at_utc':session.obtained_at_utc,'server_expires_at_utc':session.expires_at_utc,
          'maximum_server_token_lifetime_seconds':TOKEN_TTL_SECONDS,
          'expiry_note':'Server expiry is authoritative. The opt-in provider refreshes in memory before expiry.'}
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def child_environment(session):
    environment=os.environ.copy()
    environment.update(session.environment())
    # The downstream voice process has no need for the cloud model credential.
    environment.pop('DEEPSEEK_API_KEY',None)
    return environment


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--credentials',default=str(DEFAULT_CREDENTIALS))
    parser.add_argument('--session-file',default=str(DEFAULT_SESSION))
    parser.add_argument('--base-url',default=API_URL)
    parser.add_argument('--refresh',action='store_true',help='Login, verify viewer, write a private temporary session.')
    args=parser.parse_args(argv)
    try:
        validate_base_url(args.base_url)
        load_credentials(args.credentials)
        result={'private_credentials_valid':True,'credentials_printed':False,'service_started':False}
        if args.refresh:
            session=create_session(args.credentials,args.base_url)
            persist_session(session,args.session_file)
            result.update(viewer_identity_verified=True,session_file_written=True,
                          maximum_server_token_lifetime_seconds=TOKEN_TTL_SECONDS,
                          automatic_renewal='provider_opt_in_credentials_file_only')
        print(json.dumps(result,ensure_ascii=True))
        return 0
    except ViewerSessionError as exc:
        print(json.dumps({'ready':False,'error_code':exc.code,'credentials_printed':False,'service_started':False}))
        return 2
    except Exception as exc:
        print(json.dumps({'ready':False,'error_type':type(exc).__name__,'credentials_printed':False,'service_started':False}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
