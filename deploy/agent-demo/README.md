# 本地软件演示部署

当前默认入口是 **capabilities软件参赛版**：专用 `.agent-capabilities` 数据库、最新V24与新Agent工作台。显式 `--profile demo` 保留旧 `.agent-demo` 入口。两个软件profile使用相同18927/5187端口，不能同时启动。实物联调 `.hardware-live`、8000/5173和私有配置不由本启动器选择或停止。

## Windows

先安装Python 3.12、Node.js和Git LFS，确保前端V24 GLB是完整二进制。在仓库根目录：

```powershell
git lfs pull --include="frontend/public/models/utility-tunnel-v24.glb" --exclude=""
./deploy/agent-demo/manage-demo.ps1 setup
cd frontend
npm ci
cd ..
# 可选：安装本地CPU检索依赖并下载约95 MB BGE权重
./deploy/agent-demo/manage-demo.ps1 setup -Rag
./deploy/agent-demo/manage-demo.ps1 start
```

已有配置好的Python时可跳过创建和安装专用venv；启动器不修改外部Python环境：

```powershell
$python = 'D:\shixi\utility-tunnel-digital-twin\artifacts\publish-agent-qa-20261025\Scripts\python.exe'
./deploy/agent-demo/manage-demo.ps1 setup -PythonPath $python
./deploy/agent-demo/manage-demo.ps1 start -PythonPath $python
# 或使用Python入口
& $python deploy/agent-demo/manage_demo.py start --python $python
```

上面两个start是替代选项。指定外部Python时，setup只核对Django/dotenv依赖并创建私有配置，不运行pip。`-Rag`仅在启动器创建的专用venv中安装可选检索依赖；不能与外部Python安装混用。

打开 <http://127.0.0.1:5187/agent-workbench>，使用 `.agent-capabilities/users.json` 的本地账号密码。管理员账号名 `agent-eval-administrator`，运维员 `agent-eval-operator`。这些随机密码和服务密钥属于本机私有数据，不能放入参赛附件。页面必须选择真实API登录，不能使用纯前端假登录。

启动器应用迁移，通过 `prepare_agent_release` 幂等安装或升级精确V24，保留已有任务、档案和场景历史，再隐藏启动API、模拟采样、工作进程和Vite。端口冲突退出，不终止已有服务。日志在所选profile的 `{api,sampler,worker,web}.log`。初始暂停，管理员点“开始采样”。不要用评测命令的`--reset`初始化正在演示的库，它会清空对应评测数据。

## 模型调用必须显式开启

Windows/Python启动器的普通start默认清空付费模型传输凭据、关闭AnyJev路由。私有配置或父进程有密钥，也不会暗中恢复调用。不开启时仍能查看数据、模型、档案和审核记录，页面显示模型调用禁用。CI和离线检查不发起模型调用；`-NoPaidModel`保留为兼容参数。

用户明确决定进行真实模型任务后，可编辑本profile私有配置，或者显式指定仅取用模型密钥和模型标识的文件：

```powershell
./deploy/agent-demo/manage-demo.ps1 stop
./deploy/agent-demo/manage-demo.ps1 start -PythonPath $python -AllowPaidModel
# 替代选项：只读指定文件中的DEEPSEEK_API_KEY/MODEL，不复制其他凭据，不打印密钥
./deploy/agent-demo/manage-demo.ps1 start -PythonPath $python -AllowPaidModel -KeyEnvFile 'D:\私有目录\模型配置.env'
```

开启只允许明确提交的任务产生调用，不自动运行评测。`-EnableRouter`是单独的实验开关，需要本地AnyJev服务及本profile私有 `ANYJEV_URL`／`ANYJEV_TOKEN`；默认关闭，不影响三Agent主流程。

## 停止、备份与恢复

```powershell
./deploy/agent-demo/manage-demo.ps1 stop
./deploy/agent-demo/manage-demo.ps1 backup
./deploy/agent-demo/manage-demo.ps1 restore -File 'D:\备份\20261027-120000.zip'
# 旧软件profile仍使用自己的目录和配置，默认也不付费
./deploy/agent-demo/manage-demo.ps1 start -Profile demo -PythonPath $python
```

停止器核对本启动器登记的PID、启动时间、命令行散列和工作区，拒绝误杀复用PID；旧版无身份标记的记录需人工检查。启动失败只清理本次创建的子进程。就绪检查使用本机回环，不使用环境代理，并核对软件profile。

备份恢复前停止启动器并完成/取消任务。SQLite快照包含已提交WAL内容，另含演示账号、场景和模型媒体（须私密保存）；不含密钥、虚拟环境或业务库。恢复先校验profile、路径和SQLite完整性，替换前另存当前状态。capabilities不接受旧demo备份，不能跨库恢复。独立启动的服务仍应先由启动者停止。

```powershell
# 全在临时目录操作，不启动服务或调用模型
& $python -m unittest discover -s deploy/agent-demo -p 'test_manage_demo.py'
# 先停止启动器，再对软件演示库暂改阶段并验证恢复；被替换状态另存
& $python deploy/agent-demo/check_backup_restore.py --profile capabilities
```

## Docker本地包

此节为独立的旧demo容器配置，仍读取 `.agent-demo/.env`；它没有Windows启动器的付费开关。只做页面演示时保持该文件的 `DEEPSEEK_API_KEY` 为空。API镜像已显式复制精确V24运行文件，Docker上下文排除capabilities和hardware私有目录；本轮只做静态配置检查，没有启动或验证Docker容器。

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

## 护栏与受控经验升级（2026-10-27）

[功能、规则、审核与复现](../../docs/guardrails-experience-20261027/README.md)。更新后启动器自动应用新经验表迁移；既有记录不自动获批。需要禁止付费调用时使用`python deploy/agent-demo/manage_demo.py start --no-paid-model`，或PowerShell启动器增加`-NoPaidModel`。该选项仅清空本次进程模型密钥，不改写私有配置，也不移除三维模型。
