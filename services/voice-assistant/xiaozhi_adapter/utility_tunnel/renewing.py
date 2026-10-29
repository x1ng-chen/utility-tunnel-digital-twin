"""Serialized, bounded renewal for the explicit local viewer-credentials mode."""
from pathlib import Path
import threading
import time
from .client import BridgeConfig,TunnelVoiceClient,VoiceBridgeError
from .viewer_session import API_URL,ViewerSessionError,create_session,private_path,validate_base_url

_registry={}
_registry_lock=threading.RLock()


class RenewingTunnelVoiceClient:
    def __init__(self,credentials_path,base_url=API_URL,timeout=65,
                 session_factory=create_session,client_factory=TunnelVoiceClient,clock=time.monotonic):
        self.base_url=validate_base_url(base_url)
        if self.base_url!=API_URL:
            raise ViewerSessionError('fixed_local_api_required')
        if isinstance(timeout,bool) or not isinstance(timeout,int) or not 60<=timeout<=90:
            raise ViewerSessionError('invalid_timeout')
        self.credentials_path=Path(credentials_path)
        self.timeout=timeout
        self._session_factory=session_factory
        self._client_factory=client_factory
        self._clock=clock
        self._lock=threading.RLock()
        self._session=None
        self._client=None

    def _fresh(self):
        session=self._session_factory(self.credentials_path,self.base_url)
        if session.base_url!=self.base_url or session.needs_refresh(self._clock()):
            raise ViewerSessionError('fresh_viewer_session_too_short')
        self._client=self._client_factory(BridgeConfig(self.base_url,session.token,self.timeout))
        self._session=session

    def ask(self,dialogue):
        # Hold the lock across this bounded query so rotation cannot revoke a token
        # between another thread's identity check and Agent request.
        with self._lock:
            if self._session is None or self._session.needs_refresh(self._clock()):
                self._fresh()
            try:
                return self._client.ask(dialogue)
            except VoiceBridgeError as exc:
                if exc.code!='authentication_failed':
                    raise
            # A revoked/expired session gets one refresh and one retry only.
            self._session=None
            self._client=None
            self._fresh()
            return self._client.ask(dialogue)


def shared_client(credentials_path,base_url=API_URL,timeout=65):
    path=private_path(credentials_path)
    base_url=validate_base_url(base_url)
    key=(str(path).casefold(),base_url,timeout)
    with _registry_lock:
        if key not in _registry:
            _registry[key]=RenewingTunnelVoiceClient(path,base_url,timeout)
        return _registry[key]
