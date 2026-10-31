"""Deterministic, authenticated speaker-only voice controls."""
import asyncio
import json
import re
import unicodedata
import uuid

GET = "self_audio_speaker_get_volume"
SET = "self_audio_speaker_set_volume"

def parse(text):
    if not isinstance(text, str) or len(text) > 1024: return None
    if text.lstrip().startswith("{"):
        try: text = json.loads(text).get("content")
        except (ValueError, AttributeError): return None
    if not isinstance(text, str) or len(text) > 160: return None
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).rstrip("。.!！?？")
    text = re.sub(r"^(?:你好[,，]?)?小管[,，:：]?", "", text)
    text = re.sub(r"^(?:请帮我|麻烦你|麻烦|帮我|请)", "", text)
    if text in {"静音", "开启静音", "打开静音", "音量静音"}: return ("set", 0)
    if text in {"取消静音", "关闭静音", "解除静音", "恢复声音", "打开声音"}: return ("unmute", None)
    if re.fullmatch(r"(?:把)?(?:音量|声音)(?:调|开|放|再调|再)?(?:大|高)(?:一点|一些|点|些)?(?:吧)?", text) or text in {"调大音量", "提高音量", "增大音量", "大声一点"}: return ("delta", 10)
    if re.fullmatch(r"(?:把)?(?:音量|声音)(?:调|开|放|再调|再)?(?:小|低)(?:一点|一些|点|些)?(?:吧)?", text) or text in {"调小音量", "降低音量", "减小音量", "小声一点"}: return ("delta", -10)
    m = re.fullmatch(r"(?:把)?(?:音量|声音)(?:设置|设定|调整|调节|设|调|开|放)?(?:为|到|成)?(最大|最高|最小|最低)(?:吧)?", text)
    if m: return ("max", None) if m[1] in {"最大", "最高"} else ("set", 0)
    m = re.fullmatch(r"(?:把)?(?:音量|声音)(?:设置|设定|调整|调节|设|调|开|放)?(?:为|到|成)(.+?)(?:%|百分比)?(?:吧)?", text)
    if not m: return None
    raw = m[1].removeprefix("百分之"); digits = {"零":0,"〇":0,"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
    if re.fullmatch(r"[0-9]{1,3}", raw): value = int(raw)
    elif raw in {"一百", "百"}: value = 100
    elif raw and len(raw) <= 3 and all(c in digits for c in raw): value = int("".join(str(digits[c]) for c in raw))
    else:
        n = re.fullmatch(r"([一二两三四五六七八九]?)十([零〇一二两三四五六七八九]?)", raw)
        value = 10 * digits.get(n[1], 1) + digits.get(n[2], 0) if n else -1
    return ("set", value) if 0 <= value <= 100 else ("invalid", None)

def receipt(value):
    if isinstance(value, str): value = json.loads(value)
    if not isinstance(value, dict) or set(value) != {"volume", "max_volume", "unmute_volume"}: raise ValueError("invalid receipt")
    v, limit, previous = (value[k] for k in ("volume", "max_volume", "unmute_volume"))
    if any(type(x) is not int for x in (v, limit, previous)) or not 1 <= limit <= 80 or not 0 <= v <= limit or not 1 <= previous <= limit: raise ValueError("invalid receipt")
    return v, limit, previous

def current(conn, generation, sentence):
    ws = getattr(conn, "websocket", None); stop = getattr(conn, "stop_event", None)
    return bool(ws is not None and not getattr(ws, "closed", False) and getattr(ws, "close_code", None) is None and getattr(getattr(ws, "state", None), "name", "") not in {"CLOSED", "CLOSING"} and (stop is None or not stop.is_set()) and not getattr(conn, "client_abort", False) and getattr(conn, "_ut_volume_generation", None) == generation and getattr(conn, "sentence_id", None) == sentence)

async def rpc(conn, name, args):
    if name not in {GET, SET}: raise ValueError("tool denied")
    client = getattr(conn, "mcp_client", None)
    if client is None: raise ValueError("device unavailable")
    for i in range(31):
        if await client.is_ready(): break
        if i == 10:
            from core.providers.tools.device_mcp import send_mcp_initialize_message
            await asyncio.wait_for(send_mcp_initialize_message(conn), 1)
        await asyncio.sleep(0.1)
    else: raise ValueError("device unavailable")
    from core.providers.tools.device_mcp.mcp_handler import call_mcp_tool
    return await call_mcp_tool(conn, client, name, args, timeout=5)

def emit(conn, sentence, text):
    from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO
    for st, ct, detail in ((SentenceType.FIRST, ContentType.ACTION, None), (SentenceType.MIDDLE, ContentType.TEXT, text), (SentenceType.LAST, ContentType.ACTION, None)):
        conn.tts.tts_text_queue.put(TTSMessageDTO(sentence_id=sentence, sentence_type=st, content_type=ct, content_detail=detail))

def wrapper(original, *, invoke=rpc, output=emit, send=None):
    async def handle(conn, text):
        if getattr(conn, "_ut_terminal_volume_authorized", False) is not True: return await original(conn, text)
        generation = getattr(conn, "_ut_volume_generation", 0) + 1; conn._ut_volume_generation = generation
        command = parse(text)
        if command is None: return await original(conn, text)
        if getattr(conn, "client_is_speaking", False): return True
        sentence = uuid.uuid4().hex; conn.sentence_id = sentence; conn.client_abort = False
        if not hasattr(conn, "_ut_volume_lock"): conn._ut_volume_lock = asyncio.Lock()
        async with conn._ut_volume_lock:
            if not current(conn, generation, sentence): return True
            if send is None:
                from core.handle.sendAudioHandle import send_stt_message
                await send_stt_message(conn, text)
            else: await send(conn, text)
            if not current(conn, generation, sentence): return True
            reply = "音量请设为0到100之间的整数，设备目前最高80。"
            if command[0] != "invalid":
                try:
                    async with asyncio.timeout(12):
                        before, maximum, previous = receipt(await invoke(conn, GET, {}))
                        if not current(conn, generation, sentence): return True
                        target = before + command[1] if command[0] == "delta" else maximum if command[0] == "max" else previous if command[0] == "unmute" else command[1]
                        target = max(0, min(maximum, target))
                        if target != before:
                            result = await invoke(conn, SET, {"volume": target})
                            if not current(conn, generation, sentence): return True
                            if result is not True and result != "true": raise ValueError("unconfirmed")
                        after, maximum, _ = receipt(await invoke(conn, GET, {}))
                        if not current(conn, generation, sentence): return True
                        reply = ("已静音，要恢复声音时说取消静音。" if after == 0 else f"音量现在是{after}。" if after != target or before == after else f"音量已调到{after}。")
                except asyncio.CancelledError: raise
                except Exception: reply = "暂时没有确认到设备音量，请稍后再试。"
            if current(conn, generation, sentence): output(conn, sentence, reply)
        return True
    handle._ut_volume_controls_wrapper = True
    return handle

def install_volume_controls():
    from core.handle import receiveAudioHandle
    if not getattr(receiveAudioHandle.handle_user_intent, "_ut_volume_controls_wrapper", False):
        receiveAudioHandle.handle_user_intent = wrapper(receiveAudioHandle.handle_user_intent)
