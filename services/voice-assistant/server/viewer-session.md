# 本机语音专用查看者与开发会话

本机已建立专用 viewer 账号，管理员与运维员账号均未修改。随机密码保存在仓库外 D:/ut-voice/private/viewer-credentials.json；目录与文件ACL只允许当前Windows用户。不要把该文件、viewer-session.json、密码或token提交到仓库或发到聊天。

当前可选两种方式：

- 推荐本机开发：在语音服务子进程环境设置 UT_VOICE_VIEWER_CREDENTIALS_FILE 为上述JSON路径，UT_VOICE_API_URL 为 http://127.0.0.1:8000/api，移除 UT_VOICE_API_TOKEN。密码只从受限文件读取，不放入环境。provider只接受固定的这个回环API。
- 兼容原方式：不设置凭据文件，仅设置 UT_VOICE_API_TOKEN。原有40位临时token契约保持不变，过期后由运维重新提供；该模式不自动续期。

DEEPSEEK_API_KEY仅由Django后端读取。语音服务进程不需要它，启动辅助代码会从子进程环境移除该键。

## 会话生命周期

服务器TTL仍为900秒。登录响应新增非秘密字段 tokenExpiresAt 和 tokenExpiresIn；复用旧token时返回原到期时间及真实剩余秒数，没有延长任何token的有效期。

凭据文件模式使用服务端剩余秒数与本机monotonic时钟确定刷新期限，不用“刚拿到token就再活15分钟”的假设。剩余60秒前刷新；服务端若仍返回临期旧token，helper会重新确认其viewer身份，只注销这个专用viewer自己的token，再登录一次。新的会话仍临期则明确失败，不无限循环。

同一凭据文件、API和超时配置共享RLock。锁覆盖一次有界问答，避免另一个线程在身份检查和Agent请求之间撤销旧token。鉴权失败最多刷新并重试一次；网络错误、模型错误等不自动重放。角色改变或账号禁用时会停止授权。

此机制仅用于本机开发。迁移服务器时应重新配置受限凭据目录、部署身份与TLS，并实现可撤销的设备准入；不能将回环地址、Windows路径或本机密码直接搬到板子上。

## 使用辅助代码

server/viewer_session.py 是命令行入口，真正的helper随LLM provider包部署：

    & 'D:/ut-voice/voice-server-venv/Scripts/python.exe' -B 'D:/新建文件夹/utility-tunnel-digital-twin/services/voice-assistant/server/viewer_session.py'

默认只检查私有凭据结构，不启动服务、不登录。加 --refresh 登录并核对viewer，将临时session写入同一私有目录；输出只包含成功状态和TTL策略，不打印密码或token。缓存文件的服务器到期时间是权威值，provider运行时在内存续期。

导入后可调用 create_session() 得到带隐藏token repr的对象。child_environment(session)可用于一次性开发token模式；持续运行应由启动器只注入凭据文件路径，交给LLM provider续期，不必把密码或token写入启动命令行。

## 已验证范围

[账号准备](viewer-account-setup.json)记录专用viewer、非staff/非superuser以及900秒TTL；[实际问候验收](viewer-agent-test.json)已通过viewer登录、身份校验、Django Agent和DeepSeek，返回explanation_only。请求未查询现场、未生成工单。

14项helper测试覆盖旧token复用、服务器时钟差、临期撤销与再登录、格式与角色校验；8项provider测试覆盖缓存、并发仅一次刷新、401有界重试、其他失败不重放及旧token模式。另有2项Django测试确认新token与复用token的真实到期元数据。

这份验收不表示ESP32联网语音、真实麦克风ASR、动态TTS板端播放或完整语音助手已通过。
