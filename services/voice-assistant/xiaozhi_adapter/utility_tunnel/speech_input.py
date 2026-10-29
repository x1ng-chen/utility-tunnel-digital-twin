"""Conservative spelling normalization for explicit, supported business identifiers.

This does not restore missing audio or infer a station from an incomplete phrase.
The original dialogue remains untouched for ASR diagnostics.
"""
import re
import unicodedata

_DIGITS = {str(i): str(i) for i in range(10)}
_DIGITS.update(dict(zip("零〇一二三四五六七八九", "00123456789")))
_NUM = "1-5１-５一二三四五"
_ID = "A-Za-zＡ-Ｚａ-ｚ0-9０-９_"
_ALL_NUM = "0-9０-９零〇一二三四五六七八九十百千万"
_END = r"(?![" + _ID + r"零〇一二三四五六七八九十百千万-])(?![.．][" + _ALL_NUM + r"])"
_STATION = re.compile(r"(?<![" + _ID + r"-])[PpＰｐ]\s*([" + _NUM + r"])" + _END)
_STATION_SOUND = re.compile(r"(?<![" + _ID + r"-])(?:皮|屁|批)\s*([" + _NUM +
    r"])\s*(检测点|监测点|站点|站)(?!台)")
_NUMBERED_STATION = re.compile(r"(?<![" + _ID + _ALL_NUM + r".．点])(?:第([" + _NUM +
    r"])(?:个|号)?|([" + _NUM + r"])号)\s*(检测点|监测点|站点|站)(?!台)")
_MQ_SPOKEN = re.compile(r"(?<![" + _ID + r"-])M\s*Q\s*([24二四])"
    r"(\s*(?:-\s*)?[" + _ALL_NUM + r"](?:\s*[" + _ALL_NUM + r"])*)?" + _END, re.I)
_DEVICE = re.compile(r"(?<![" + _ID + r"-])(MQ2|MQ4|CO|FLAME|LEVEL|SHT|O2|CTRL|FAN)"
    r"\s*-\s*([0-9零〇一二三四五六七八九]{1,2})" + _END, re.I)
_COMPACT_DEVICE = re.compile(r"(?<![" + _ID + r"-])(MQ2|MQ4|CO|FLAME|LEVEL|SHT|O2|CTRL|FAN)"
    r"\s*((?:0|零|〇)\s*[1-9一二三四五六七八九])" + _END, re.I)
# Physical labels from station-inventory.json; normalization never changes a
# physical label into a different logical asset code (e.g. MQ2-01 -> SMOKE-01).
_KNOWN = {f"{family}-{i:02}" for family, maximum in
    (("MQ2", 5), ("MQ4", 5), ("CO", 5), ("FLAME", 5), ("LEVEL", 4),
     ("SHT", 4), ("O2", 3), ("CTRL", 4), ("FAN", 2))
    for i in range(1, maximum + 1)}
_TRANSPORT = re.compile(r"地铁|火车|高铁|公交|列车|站台")


def _digit(value):
    return _DIGITS[unicodedata.normalize("NFKC", value)]


def normalize_business_text(text):
    if not isinstance(text, str) or not text or text.lstrip().startswith(("{", "[")):
        return text
    result = _STATION.sub(lambda m: "P" + _digit(m[1]), text)
    result = _STATION_SOUND.sub(lambda m: "P" + _digit(m[1]) + m[2], result)
    # Do not reinterpret an ordinary transport station as a tunnel station.
    if not _TRANSPORT.search(text):
        result = _NUMBERED_STATION.sub(
            lambda m: "P" + _digit(m[1] or m[2]) + m[3], result)
    def mq_label(match):
        family = "MQ" + _digit(match[1])
        serial = match[2]
        if not serial:
            return family
        digits = "".join(ch for ch in serial if not ch.isspace() and ch != "-")
        # No separator is only unambiguous with a two-digit, zero-padded index.
        if not serial[0].isspace() and not serial.startswith("-") and not digits.startswith(("0", "零", "〇")):
            return match[0]
        if not 1 <= len(digits) <= 2:
            return match[0]
        try:
            value = int("".join(_digit(ch) for ch in digits))
        except KeyError:
            return match[0]
        candidate = family + "-" + f"{value:02}"
        return candidate if candidate in _KNOWN else match[0]
    result = _MQ_SPOKEN.sub(mq_label, result)

    def device(match):
        digits = "".join(_DIGITS[d] for d in match[2] if not d.isspace())
        candidate = match[1].upper() + "-" + f"{int(digits):02}"
        return candidate if candidate in _KNOWN else match[0]
    result = _DEVICE.sub(device, result)
    return _COMPACT_DEVICE.sub(device, result)


def normalize_latest_user_turn(dialogue):
    """Copy only a final plain user turn; validation still belongs to the bridge."""
    if not isinstance(dialogue, list) or not dialogue:
        return dialogue
    last = dialogue[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        return dialogue
    content = last.get("content")
    normalized = normalize_business_text(content)
    if normalized == content:
        return dialogue
    return [*dialogue[:-1], {**last, "content": normalized}]
