import json,tempfile
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from test_voice_roundtrip import (Capture,RoundtripError,FRAME_BYTES,hello_message,
    validate_hello,pcm_frames,parse_json_message,DeviceCredentials,validate_ota,load_device_credentials,WS_URL)

SESSION='test-session-only'
EXPECTED='你好这是管廊本地语音测试'


def event(kind,**extra):
    return json.dumps({'type':kind,'session_id':SESSION,**extra})


class RoundtripContractTests(unittest.TestCase):
    def capture(self):
        return Capture(SESSION,lambda packet:b'\x00\x10'*(FRAME_BYTES//2))

    def test_hello_disables_capabilities_and_requires_matching_audio(self):
        hello=hello_message()
        self.assertEqual(hello['features'],{'mcp':False,'aec':False})
        self.assertEqual(validate_hello({**hello,'session_id':SESSION}),SESSION)
        hello['audio_params']['sample_rate']=24000
        with self.assertRaises(RoundtripError):
            validate_hello({**hello,'session_id':SESSION})

    def test_pcm_frame_padding_preserves_input(self):
        pcm=b'\x01\x00'*1000
        frames=pcm_frames(pcm)
        self.assertEqual(len(frames),2)
        self.assertTrue(all(len(frame)==FRAME_BYTES for frame in frames))
        self.assertEqual(b''.join(frames)[:len(pcm)],pcm)
        self.assertEqual(b''.join(frames)[len(pcm):],b'\0'*(FRAME_BYTES*2-len(pcm)))
        with self.assertRaises(RoundtripError):pcm_frames(b'x')

    def test_complete_turn_distinguishes_emotion_from_reply_text(self):
        cap=self.capture()
        cap.feed(event('stt',text=EXPECTED))
        cap.feed(event('tts',state='start'))
        cap.feed(event('llm',text='🙂',emotion='happy'))
        cap.feed(event('tts',state='sentence_start',text='你好，测试已收到。'))
        cap.feed(b'encoded-test-packet')
        cap.feed(event('tts',state='stop'))
        result=cap.summary()
        self.assertTrue(result['roundtrip_passed'])
        self.assertEqual(result['reply_text'],'你好，测试已收到。')
        self.assertEqual(result['reply_opus_packets'],1)
        self.assertEqual(result['asr_similarity'],1.0)

    def test_audio_before_start_oversized_packet_and_bad_decode_rejected(self):
        cap=self.capture()
        with self.assertRaises(RoundtripError):cap.feed(b'audio')
        cap.feed(event('tts',state='start'))
        with self.assertRaises(RoundtripError):cap.feed(b'x'*2049)
        cap=Capture(SESSION,lambda _:b'wrong-duration')
        cap.feed(event('tts',state='start'))
        with self.assertRaises(RoundtripError):cap.feed(b'opus')

    def test_cross_session_and_capability_messages_rejected(self):
        cap=self.capture()
        with self.assertRaises(RoundtripError):
            cap.feed(json.dumps({'type':'stt','session_id':'other','text':'hello'}))
        for kind in ['mcp','iot','server','error']:
            with self.subTest(kind=kind),self.assertRaises(RoundtripError):
                cap.feed(event(kind))

    def test_empty_tts_or_application_error_is_not_a_success(self):
        cap=self.capture()
        cap.feed(event('stt',text=EXPECTED));cap.feed(event('tts',state='start'))
        cap.feed(event('llm',text='🙂',emotion='happy'))
        cap.feed(event('tts',state='sentence_start',text='管廊查询失败，请稍后重试。'))
        cap.feed(b'opus');cap.feed(event('tts',state='stop'))
        self.assertFalse(cap.summary()['roundtrip_passed'])
        self.assertTrue(cap.summary()['fallback_error_reply_detected'])
        cap=self.capture()
        cap.feed(event('tts',state='start'));cap.feed(event('tts',state='stop'))
        self.assertFalse(cap.summary()['roundtrip_passed'])

    def test_private_device_schema_and_repr_do_not_expose_secrets(self):
        token='a'*64
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'device.json'
            data={'schema':'ut.voice.devices.v1','devices':[{'device_id':'11:22:33:44:55:66',
                'client_id':'204b7c1f-9251-48c5-9c44-bdaf282842d4','token':token}]}
            path.write_text(json.dumps(data),encoding='utf-8')
            credentials=load_device_credentials(path,root)
            self.assertNotIn(token,repr(credentials))
            self.assertNotIn('11:22:33:44:55:66',repr(credentials))
            self.assertEqual(credentials.headers(websocket=True)['Protocol-Version'],'1')
            data['devices'].append(data['devices'][0])
            path.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(RoundtripError):load_device_credentials(path,root)

    def test_ota_never_redirects_credentials_to_another_endpoint(self):
        credentials=DeviceCredentials('11:22:33:44:55:66','client','a'*64)
        data={'websocket':{'url':WS_URL,'token':'a'*64,'version':1},'firmware':{'url':''}}
        self.assertEqual(validate_ota(data,credentials),WS_URL)
        data['websocket']['url']='ws://192.168.1.2:8941/xiaozhi/v1/'
        with self.assertRaises(RoundtripError):validate_ota(data,credentials)
        data['websocket']['url']=WS_URL
        data['websocket']['token']='b'*64
        with self.assertRaises(RoundtripError):validate_ota(data,credentials)

    def test_non_object_and_large_json_rejected(self):
        for value in ['[]','not-json','x'*65537]:
            with self.subTest(length=len(value)),self.assertRaises(RoundtripError):
                parse_json_message(value)


if __name__=='__main__':unittest.main()
