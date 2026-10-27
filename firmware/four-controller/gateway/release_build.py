"""Build metadata only. Never reads a Wi-Fi/MQTT credential."""
import os,re
Import('env')
identity=os.environ.get('UT_FIRMWARE_BUILD_ID','development')
if not re.fullmatch(r'[A-Za-z0-9._-]{1,40}',identity):
    raise RuntimeError('Invalid UT_FIRMWARE_BUILD_ID')
env.Append(CPPDEFINES=['UT_RUNTIME_CONFIG_ONLY',('UT_BUILD_ID',env.StringifyMacro(identity))])
