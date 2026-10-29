# 本地 AnyJev 决策服务

它只从服务端给定的只读取证检查中选一项。Django 再核验选项并实际执行工具。它不能生成工具参数、批准动作、控制硬件或替代 DeepSeek 的取证／诊断／复核角色。服务默认关闭，启动服务也不会自动启用 Django 路由。

实现固定使用 [AnyJev](https://github.com/nokia-applied-research/AnyJev) 提交 `35311c58955716cb8955ce1368a665988bc63735`、[Tacit-1.7B](https://huggingface.co/morriszjm/Tacit-1.7B) 修订 `1cb46fff0ffeefc4965455185074be5c62adccf7`。不是 TypeSafe 托管 API。版本、来源和权重散列见 [model.lock.json](../../services/decision-router/model.lock.json)。

## Windows 安装与启动

在仓库根目录执行。默认运行目录为 `D:\shixi\utility-tunnel-runtime\anyjev`，必须位于 Git 工作区以外；也可通过 `-RuntimeRoot` 指定其他目录。`-Python` 指向已有可用的 Python 3.12，安装器会另外建立虚拟环境，不修改 Django 环境。

```powershell
./deploy/decision-router/install.ps1 -Python 'C:\你的Python环境\Scripts\python.exe'
./deploy/decision-router/start.ps1
```

本机已完成安装、权重 SHA256 校验和实际 CUDA 推理。权重文件 3,441,185,608 字节；本轮联合流程实测最大 PyTorch 已分配显存约 3483 MiB、保留显存约 3562 MiB。启动器要求空闲显存至少 4608 MiB，给加载和推理留余量。这不是所有设备的内存下限，也未测量全机 RAM 峰值。需要支持 CUDA 的显卡；没有 CPU 偷偷卸载、OOM 重试或付费云端回退。

启动会预加载模型。另开 PowerShell 检查就绪状态；令牌不应粘贴到聊天、截图或公共文件：

```powershell
$runtime = 'D:\shixi\utility-tunnel-runtime\anyjev'
$routerToken = (Get-Content -LiteralPath "$runtime\service-token.txt" -Raw).Trim()
Invoke-RestMethod 'http://127.0.0.1:8110/health' -Headers @{Authorization="Bearer $routerToken"}
```

准备好后，在**启动 Django API 和工作进程的同一个环境**配置：

```powershell
$env:ANYJEV_ENABLED = 'true'
$env:ANYJEV_URL = 'http://127.0.0.1:8110'
$env:ANYJEV_TOKEN = $routerToken
```

同一任务最多增加三次路由请求；实际 HTTP 尝试，包括超时失败，计入原有 12 次模型调用和 120 秒总期限。工具仍计入 12 次工具上限。输入超过 2048 token、选中“不确定”、分布间距不足、不可用或绑定不匹配时记录回退，继续原有受限取证。分布不是经过本项目标定的事故概率。

服务仅监听 `127.0.0.1:8110`，不跟随重定向，不使用环境代理；请求和结果绑定请求编号、输入及选项散列、模型修订与来源。一次只执行一个推理请求。原始请求和令牌不写入服务日志。

停止**本启动器自己的进程**，释放显存：

```powershell
./deploy/decision-router/stop.ps1
```

停止器核对 PID、启动时间和命令行，拒绝误杀复用 PID 的其他程序。删除进程记录不等于停止模型。

## 不付费的检查与显式模型评测

```powershell
# 使用 Django 环境即可；只是 HTTP 契约桩，不加载权重
python -m unittest discover -s services/decision-router -p 'test_*.py'
# 没有 --local-model 时只列出用例，不发出推理请求
python tools/anyjev/evaluate_local.py
# 明确调用已启动的本地模型；不调用 DeepSeek
python tools/anyjev/evaluate_local.py --local-model --suite holdout
```

[完整功能、验收分层和原始记录](../../docs/agent-capabilities-20261029/README.md)。当前小模型检查选择仍有明显回退和未命中，不能据此宣传提高诊断准确率或降低处置成本。

## 部署范围

本轮验证的是 Windows 原生服务＋同机 Django。原有 Docker 包继续默认禁用 AnyJev；容器里的 `127.0.0.1` 不等于 Windows 主机。尚未提供或验证跨容器 GPU 部署，不能简单打开环境变量就声称容器已接通。`service-token.txt`、模型权重、pip 缓存、私有 `.env` 和日志不进入 Git 或公共证据包。
