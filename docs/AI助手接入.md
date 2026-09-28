# 页面 AI 助手

平台登录后的页面右下角提供 DeepSeek 助手。它可解释页面用途和一般运维流程；不会自动读取实时遥测、数据库详情或执行设备控制。页面只提交用户输入的最近五轮对话和当前页面名称，聊天记录仅在当前浏览器内存中保留，退出登录时清除。

## 后端配置

在后端的未跟踪 `backend/.env` 中配置：

```dotenv
DEEPSEEK_API_KEY=在本地填入你的密钥
DEEPSEEK_MODEL=deepseek-flash
AI_ASSISTANT_RATE_LIMIT=20/hour
```

配置后重启 Django 服务。密钥只在后端使用；不要放进 `frontend/.env`、任何 `VITE_` 变量或浏览器代码。页面需要登录正式数据服务，演示登录模式不会调用付费接口。

容器部署时，在服务端环境提供同名变量；生产 Compose 仅向 `api` 容器传递密钥，网页构建和浏览器都不会接收它。

后端的 `POST /api/assistant/chat/` 要求 Bearer 登录凭据。每次最多接收 12 条消息、每条最多 2000 字、总计最多 8000 字；只接受 `user` 和 `assistant` 角色，最后一条必须由用户发送。默认每名用户每小时最多请求 20 次。

DeepSeek 接口地址固定为 `https://api.deepseek.com/chat/completions`，默认使用 `deepseek-flash` 非思考模式；如需更强的模型，可将 `DEEPSEEK_MODEL` 设为 `deepseek-v4-pro`。助手回复仅供参考，现场状态以设备、告警和工单页面的实际记录及人工核查为准。
