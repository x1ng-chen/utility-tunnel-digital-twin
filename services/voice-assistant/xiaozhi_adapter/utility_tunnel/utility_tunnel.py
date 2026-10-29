"""Copy this package into xiaozhi-server/core/providers/llm/utility_tunnel/."""
import os
from core.providers.llm.base import LLMProviderBase
from .client import BridgeConfig,TunnelVoiceClient,VoiceBridgeError
from .renewing import shared_client
from .viewer_session import ViewerSessionError
from .speech_input import normalize_latest_user_turn


class LLMProvider(LLMProviderBase):
    def __init__(self,config):
        credentials_path=os.environ.get('UT_VOICE_VIEWER_CREDENTIALS_FILE','').strip()
        if credentials_path:
            self.client=shared_client(credentials_path,
                os.environ.get('UT_VOICE_API_URL',config.get('platform_url','http://127.0.0.1:8000/api')),
                config.get('request_timeout_seconds',65))
        else:
            # Existing explicit short-lived token deployments retain their contract.
            self.client=TunnelVoiceClient(BridgeConfig.from_environment(config))

    def response(self,session_id,dialogue,**kwargs):
        try:
            yield self.client.ask(normalize_latest_user_turn(dialogue)).text
        except VoiceBridgeError as exc:
            yield str(exc)
        except ViewerSessionError:
            yield '语音查询会话暂不可用，请检查本机查看者配置。'

    def response_with_functions(self,session_id,dialogue,functions=None):
        # All operations tools remain inside the authenticated Django Agent.
        for text in self.response(session_id,dialogue):
            yield text,None
