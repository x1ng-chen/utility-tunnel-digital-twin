# 本地软件演示部署

先安装Python 3.12、Node.js和Git LFS，确保V17 GLB是真实文件而非LFS指针。以下脚本均限定本仓库 `.agent-demo`，保留业务及既有评测库。

## Windows

在仓库根目录：

```powershell
./deploy/agent-demo/manage-demo.ps1 setup
cd frontend
npm ci
cd ..
# 可选：安装本地CPU检索依赖并下载约95 MB BGE权重
./deploy/agent-demo/manage-demo.ps1 setup -Rag
# 编辑 .agent-demo/.env，填写自己的DeepSeek密钥；不要提交密钥
./deploy/agent-demo/manage-demo.ps1 start
```

打开 <http://127.0.0.1:5187/agent-workbench>，使用 `.agent-demo/users.json` 的本地账号密码。管理员账号名 `agent-eval-administrator`，运维员 `agent-eval-operator`。这些随机密码和服务密钥属于本机私有数据，不能放入参赛附件。页面必须选择真实API登录，不能使用纯前端假登录。

启动器进行迁移及一次初始化，隐藏运行API、模拟采样、工作进程和Vite；端口冲突时退出，不终止已有服务。日志在 `.agent-demo/{api,sampler,worker,web}.log`。默认暂停，管理员点“开始采样”。模型只在明确提交任务后调用；未配密钥则任务失败并记录原因。

```powershell
./deploy/agent-demo/manage-demo.ps1 stop
./deploy/agent-demo/manage-demo.ps1 backup
./deploy/agent-demo/manage-demo.ps1 restore -File 'D:\备份\20261027-120000.zip'
```

备份恢复前停止启动器并完成/取消任务。备份含演示数据库、模型媒体及演示账号（须私密保存），不含密钥、虚拟环境或业务库；恢复前保留当前数据备份，并拒绝越界归档路径。独立启动的服务应先由启动者停止。

离线验证可运行 `.agent-demo/venv/Scripts/python.exe deploy/agent-demo/check_backup_restore.py`，它会在演示会话中暂改阶段、恢复指定备份，并核对被替换状态被单独备份。此检查只操作演示库。

## Docker本地包

```powershell
# 先创建 .agent-demo/.env，模型未配置时不触发调用
docker compose -f deploy/agent-demo/compose.yml up --build
# 可选镜像内CPU检索依赖，权重需先通过 setup_knowledge.py 下载
$env:INSTALL_RAG='1'
docker compose -f deploy/agent-demo/compose.yml up --build
```

浏览器同样访问5187。演示数据在专用named volume，与Windows本地演示库也不共用。容器内路径保留 `/app/backend`，因此隔离目录严格为 `/app/.agent-demo`。基础镜像不装向量依赖时明确降级关键词；不要把镜像可构建配置当作容器运行通过。此包使用本地开发配置，仅绑定回环端口；公网部署另行安排。

## 测试、真实评测与证据

```powershell
cd backend
../.agent-demo/venv/Scripts/python.exe manage.py test operations --noinput
../.agent-demo/venv/Scripts/python.exe manage.py evaluate_sprint --settings=config.sprint_eval_settings --suite smoke
# 下列命令明确产生供应商调用费用
../.agent-demo/venv/Scripts/python.exe manage.py evaluate_sprint --settings=config.sprint_eval_settings --suite composite --mode paired --live --confirm-test-proposals
../.agent-demo/venv/Scripts/python.exe manage.py evaluate_sprint --settings=config.sprint_eval_settings --suite regression --mode multi --live
cd ..
.agent-demo/venv/Scripts/python.exe deploy/agent-demo/check_retrieval.py
npm ci --prefix deploy/agent-demo/browser-tests
npx --prefix deploy/agent-demo/browser-tests playwright install chromium
node deploy/agent-demo/browser-tests/check.mjs
```

浏览器检查需要本地服务已启动，执行真实HTTP、桌面/手机截图及65秒暂停恢复，不调用模型。真实模型结果单独保存在 `.agent-eval-sprint/runs`，包含快照、模型、真实Token、耗时、失败与程序确认的测试工单号。普通问答基线使用 `evaluate_plain_sprint --packets runs/<同批UTC前缀> --live`。费用以供应商账单为准，人工评分模板在参赛文档目录。

最终集成验收使用 `config.sprint_final_eval_settings`，独立保存在 `.agent-eval-sprint/final/.agent-eval-sprint/runs`，与迭代批次分开。当前最终模型验收因HTTP 402中断，补足额度前不要重复启动；401/402/403会中止整个批次并保留已有记录。S05为显式受控超时桩，统计时与供应商真实请求分开。
