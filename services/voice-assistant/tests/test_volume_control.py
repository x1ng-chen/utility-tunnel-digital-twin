import asyncio
import importlib.util
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('voice_volume', Path(__file__).resolve().parents[1] / 'server' / 'volume_control.py')
v = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v
spec.loader.exec_module(v)

class VolumeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.value = 40
        self.calls = []
        self.replies = []
        self.conn = SimpleNamespace(_ut_terminal_volume_authorized=True, stop_event=threading.Event(), websocket=SimpleNamespace(closed=False, close_code=None), client_is_speaking=False, client_abort=False, sentence_id='old')
    async def original(self, conn, text): return 'ordinary'
    async def send(self, conn, text): pass
    async def rpc(self, conn, name, args):
        self.calls.append((name, args))
        if name == v.SET:
            self.value = args['volume']
            return 'true'
        return {'volume': self.value, 'max_volume': 80, 'unmute_volume': 40}
    def handler(self, rpc=None):
        return v.wrapper(self.original, invoke=rpc or self.rpc, output=lambda c,s,t: self.replies.append(t), send=self.send)
    def test_commands_are_exact_and_numbers_bounded(self):
        for text, expected in [('声音大一点',('delta',10)), ('音量调到五十',('set',50)), ('取消静音',('unmute',None)), ('音量调到100',('set',100)), ('音量调到-5',('invalid',None)), ('音量调到50然后开风机',('invalid',None)), ('不要调大音量',None), ('P1状态',None)]:
            with self.subTest(text=text): self.assertEqual(v.parse(text), expected)
    async def test_authorized_set_reads_back_actual_value(self):
        await self.handler()(self.conn, '音量调到50')
        self.assertEqual(self.calls, [(v.GET, {}), (v.SET, {'volume':50}), (v.GET,{})])
        self.assertEqual(self.replies, ['音量已调到50。'])
    async def test_cap_and_unauthorized_delegate(self):
        h = self.handler()
        await h(self.conn, '音量调到100')
        self.assertEqual(self.value, 80)
        self.conn._ut_terminal_volume_authorized = False
        count = len(self.calls)
        self.assertEqual(await h(self.conn, '静音'), 'ordinary')
        self.assertEqual(len(self.calls), count)
    async def test_failure_never_claims_success(self):
        async def fail(conn, name, args): raise RuntimeError('private failure')
        await self.handler(fail)(self.conn, '音量调到50')
        self.assertIn('没有确认', self.replies[0])
        self.assertNotIn('private', self.replies[0])
    async def test_new_question_cancels_outstanding_command(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def blocking(conn, name, args):
            started.set()
            await release.wait()
            return {'volume':40, 'max_volume':80, 'unmute_volume':40}
        h=self.handler(blocking)
        task=asyncio.create_task(h(self.conn, '声音大一点'))
        await started.wait()
        self.assertEqual(await h(self.conn, 'P1状态'), 'ordinary')
        release.set()
        await task
        self.assertFalse(self.replies)
        self.assertEqual(self.value, 40)

if __name__ == '__main__': unittest.main()