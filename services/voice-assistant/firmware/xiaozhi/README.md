# ESP32-S3 小管固件

最新界面和音量控制：待机整屏双眼；连接、聆听时双眼缩小到左侧，右侧状态与字幕；回答时右侧改为嘴巴和声波动画，不显示文字。用户确认两种布局和语音调音正常。音量0–80保存于NVS，唤醒和停止回应不再重置音量；两个MCP工具仅用于本机语音板音量，服务端配置仍不启用管廊控制工具。129项语音回归测试通过。

此前应用（2026-10-29）音量80，用户确认清楚；保留双唤醒词和两个停止词。停止控制现覆盖Speaking和Listening；用户确认两种场景均可回复停止确认后回到待机。最新构建及实物验收见 [停止状态修复](stop-states-build-report.json)。正常网络唤醒回应尾音150ms，热输入不再重复等120ms，冷输入保持原延迟。显式热路径等待预计减少270ms，不代表已量化P1识别准确率。

本次只更新0x20000应用，assets、Wi-Fi、设备凭据与运行时otadata保留；音量设置由codec按用户要求更新。四个静态镜像核验通过。记录见 [构建](volume80-build-report.json)、[来源](volume80-source-check.json)、[实物与用户反馈](volume80-test-report.json)。DeepSeek和表达优化位于服务器侧。

## 适配目标

- 专用 ESP32-S3 N16R8；外接 I²S 麦克风和 MAX98357A。
- 麦克风 16 kHz、功放 48 kHz，独立 I²S 时钟，固定左声道。
- 启用 I²C OLED（SDA41/SCL42、100kHz），探测 0x3C/0x3D，暂按 SSD1306-compatible 128×32 驱动；0x3C 实物文字与状态已通过。初始化失败退回 NoDisplay；保持 NoLed，只使用 BOOT 键。
- 开机恢复上次音量（首次默认80、允许静音0），运行时请求限制为0–80；用户确认喇叭/功放为卖家配套，额定规格仍未知。
- 离线自测片段sdkconfig.voice.defaults仅用于历史自测；当前使用sdkconfig.voice.online.defaults，生成配置须确认离线开关关闭。
- 当前联网模式不启用BOOT手动喇叭测试；唤醒后本地回应“我在呀，你说！”。历史测试选项保留在离线模式。
- 当前注册两个唤醒命令ni hao xiao guan / xiao guan；中文MultiNet7，阈值初值20。联网模式另注册两条停止命令及“声音大一点/小一点”音量命令。

引脚、电源、喇叭输出和照片识别见 [接线说明](../../hardware/README.md)。

## 固定源码与工具链要求

固件固定为 [78/xiaozhi-esp32 commit c435f99a88066029ec2dbd2d758c8cc9d051565b](https://github.com/78/xiaozhi-esp32/tree/c435f99a88066029ec2dbd2d758c8cc9d051565b)，不是持续跟随 main。
[`upstream.lock.json`](upstream.lock.json) 记录版本及未完成的验证项。

该版本要求 ESP-IDF >=6.0.1，上游推荐 `release/v6.1` 分支；不使用 IDF 5.x。
Windows 可通过 [Espressif Installation Manager](https://docs.espressif.com/projects/idf-im-ui/en/latest/) 安装。首次成功构建时须将实际 ESP-IDF commit 与生成的组件锁文件一并记录；本次已记录 SDK 精确 commit，并保存相邻的 `dependencies.lock`。

为减轻 Windows 路径长度/编码问题，独立固件工作目录建议用短英文路径，如 `D:\ut-voice\xiaozhi-esp32`。以下命令在已激活 ESP-IDF 的 PowerShell 中运行；源工程使用独立新克隆，不覆盖已有固件工程：

```powershell
$voiceAdapter = 'D:\新建文件夹\utility-tunnel-digital-twin\services\voice-assistant\firmware\xiaozhi'
$voiceFirmware = 'D:\ut-voice\xiaozhi-esp32'

git clone https://github.com/78/xiaozhi-esp32.git $voiceFirmware
if ($LASTEXITCODE -ne 0) { throw 'clone failed' }
git -C $voiceFirmware checkout --detach c435f99a88066029ec2dbd2d758c8cc9d051565b
if ($LASTEXITCODE -ne 0) { throw 'checkout failed' }

git -C $voiceFirmware apply --check "$voiceAdapter\register-board.patch"
if ($LASTEXITCODE -ne 0) { throw 'registration patch does not match' }
git -C $voiceFirmware apply "$voiceAdapter\register-board.patch"
if ($LASTEXITCODE -ne 0) { throw 'registration patch failed' }

Copy-Item -LiteralPath "$voiceAdapter\overlay\main\boards\utility-tunnel-s3" -Destination "$voiceFirmware\main\boards" -Recurse
Copy-Item -LiteralPath "$voiceAdapter\sdkconfig.voice.online.defaults" -Destination "$voiceFirmware\sdkconfig.utility-tunnel"
Copy-Item -LiteralPath "$voiceAdapter\dependencies.lock" -Destination "$voiceFirmware\dependencies.lock"
```

补丁注册新板型，并添加离线/手动播放路径与播放队列的同步修正，共涉及九个上游文件，包括CMake/Kconfig、application、audio_service、自定义命令识别、OLED、OTA和WebSocket；其他板型不启用本板测试选项。`config.json` 保留板型元数据；本次使用下面的手动 idf.py 流程保留用户唤醒配置。

## 配置、重复构建

离线自测可以保留 `CONFIG_OTA_URL` 占位值。以后关闭离线模式、改为完整助手之前，再把复制后的 `sdkconfig.utility-tunnel` 与生成配置中的 `CONFIG_OTA_URL` 设置为自己的语音服务 OTA/设备发现地址，并配置设备鉴权。
当前 `voice-endpoint.invalid` 是故意不可用的占位域名；离线模式不执行网络启动。正常模式若使用它会长时间重试，不能完成联网问答。还须检查旧 NVS 的 `wifi.ota_url`，因为它可能覆盖编译默认值；不能仅凭占位域名认定旧设置已清除。它不是 Django `/api/assistant/chat/` 地址。现有 Django 令牌只存放在语音服务器，不写入板端。

```powershell
Set-Location -LiteralPath $voiceFirmware
$voiceBuildArgs = @(
  '-B', 'build-utility-tunnel',
  '-D', 'IDF_TARGET=esp32s3',
  '-D', 'SDKCONFIG=sdkconfig.utility-tunnel.generated',
  '-D', 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.esp32s3;sdkconfig.utility-tunnel',
  '-D', 'CMAKE_NINJA_FORCE_RESPONSE_FILE=ON'
)
idf.py @voiceBuildArgs reconfigure
if ($LASTEXITCODE -ne 0) { throw 'reconfigure failed' }
idf.py @voiceBuildArgs build
if ($LASTEXITCODE -ne 0) { throw 'build failed' }
```

单独的生成配置和 build 目录用于避免复用其他板型的旧 sdkconfig。首次构建会下载组件和模型。在本机曾遇到默认组件源停滞，已按乐鑫文档使用 `IDF_COMPONENT_STORAGE_URL=https://components-file.espressif.cn` 恢复下载；重复构建脚本只在当前进程设置此官方源。若已经生成过配置，改 defaults 不一定覆盖现有值，应同步检查生成配置或通过 menuconfig 调整。

不要运行 `scripts/build.py --wake-word "ni hao guan lang"`：该参数用于上游模型名/别名选择，不接受任意拼音，且其选择逻辑可能关闭自定义唤醒分支。

本机已准备好源码时，可直接运行 [`build-voice.ps1`](build-voice.ps1)。脚本默认-Mode Online；-Mode Offline使用独立生成配置和构建目录，拒绝混用模式，并强制Python UTF-8。它会检查八个板级源码/音频覆盖文件是否一致、激活指定 SDK 并重新配置/编译，日志写入固件目录旁的 `logs/`；不执行烧录。其他电脑通过 `-FirmwarePath`、`-ActivationScript` 指定路径。

## 模型打包与构建验收

只填写拼音不会自动拥有中文识别模型。本配置显式选择：
```ini
CONFIG_USE_CUSTOM_WAKE_WORD=y
CONFIG_SR_MN_CN_MULTINET7_QUANT=y
CONFIG_SR_MN_EN_NONE=y
CONFIG_FLASH_DEFAULT_ASSETS=y
```

固定版本的资源生成器会将中文选项映射为 `mn7_cn` 和 `fst`，将拼音、显示文字和阈值写入资源索引的 `multinet_model`。上游依赖清单指定 ESP-SR 2.4.7；依赖下载后仍需核对实际 Kconfig 与文件，不能把配置片段当成已经完成的资源包。

构建通过的条件包括：

1. 生成配置保留专用板、16MB Flash、Octal PSRAM、中文MultiNet、主词ni hao xiao guan和Online/Offline所选模式。当前Online模式关闭离线自测；第二wake别名xiao guan由板级命令清单注册。
2. `managed_components/espressif__esp-sr/model/multinet_model/` 中确有 `mn7_cn` 和 `fst` 资源，资源生成日志确实加入二者。该版本缺资源可能只有 warning。
3. 资源索引含srmodels和multinet_model，主词ni hao xiao guan、显示“你好，小管”、阈值0.2。板端明确替换为两个wake别名；联网另注册“不用说了/闭嘴”。
4. 应用、分区表与语音资源均能放入所选 16MB 分区布局；不能只检查应用 bin 或 assets 文件是否存在。
5. 首次烧录前识别串口并备份原 Flash，写入完整布局与 assets。布局、资源均核对一致的后续音量升级只更新应用；校验 bootloader、分区表、应用、assets 四个静态镜像，运行时 otadata 按记录与 CRC 核对，不与全 FF 初始模板强制比较或覆盖。

## 首次离线实物验收（历史）

软件编译和桥接单测不能验证音频硬件。首次只接 I²S 麦克风和 USB，观察：

```text
OFFLINE TEST: say ni hao guan lang; BOOT re-arms detection
OFFLINE MIC: samples=... rms=... peak=...
OFFLINE WAKE DETECTED: 你好管廊
```

这些提示和唤醒事件已在用户实物上观察，详见 [实物测试记录](device-test.md)。先验证安静/说话时数字幅度变化，再验证多次唤醒和 BOOT 重新启用。始终为 0 或持续满幅需要检查供电、左右槽和模块兼容性。

用户确认配套功放/喇叭后，已验证 BOOT 低音量输出；音量 5 清楚但小，10 仍小，20 已由用户确认合适、清楚。详见 [喇叭测试](speaker-test.md)。联网阶段关闭 `UTILITY_TUNNEL_OFFLINE_WAKE_TEST`，确认实际服务地址/旧 NVS/设备鉴权，再验证 ASR、Agent、TTS。当前本地播报停止命令已实测，噪声和回声干扰下的长期命中率仍待测；AEC、监听期间重复唤醒和音频调试上传均未开启。

## 实现依据

- [固定版本板级适配说明](https://github.com/78/xiaozhi-esp32/blob/c435f99a88066029ec2dbd2d758c8cc9d051565b/docs/custom-board_zh.md)
- [自定义唤醒 Kconfig](https://github.com/78/xiaozhi-esp32/blob/c435f99a88066029ec2dbd2d758c8cc9d051565b/main/Kconfig.projbuild)
- [资源打包脚本](https://github.com/78/xiaozhi-esp32/blob/c435f99a88066029ec2dbd2d758c8cc9d051565b/scripts/build_default_assets.py)
- [解码与重采样](https://github.com/78/xiaozhi-esp32/blob/c435f99a88066029ec2dbd2d758c8cc9d051565b/main/audio/audio_service.cc)
- [MAX98357A/B 支持的 LRCLK 采样率](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf)

## 首次唤醒构建快照（2026-10-26）

- 固件：ESP-IDF 6.0.1 / commit `8c19b156084a0753687347cca1f5355782893533`，专用无屏板型，离线自测开关启用。
- `xiaozhi.bin`：1855680 字节，小于 4032 KiB 应用分区。
- `generated_assets.bin`：2951621 字节，小于 8 MiB 资源分区。
- 已读取并校验资源包校验和、`index.json` 与模型头：模型确有 `mn7_cn`、`fst`，命令与显示名是 `ni hao guan lang` / “你好管廊”，阈值 0.2。
- [`build-report.json`](build-report.json) 记录各文件 SHA-256 和实际写入地址；本机产物目录是 `D:\ut-voice\xiaozhi-esp32\build-utility-tunnel`。
- 固件源码 Git 克隆遇到超时，实际使用 GitHub 官方固定提交归档；归档哈希记录在 `upstream.lock.json`。
- 20 项服务端文字桥接单测通过；离线采音与唤醒另有实物记录。该快照不含手动播放测试；完整联网助手和 ASR/TTS 仍未验证。

当前喇叭状态见 [喇叭测试](speaker-test.md)，播放构建哈希见 [speaker-build-report.json](speaker-build-report.json)。[实物测试记录](device-test.md) 保留首次采音与唤醒结果；`build-report.json` 与已分发固件包保留构建/打包时的快照。

## OLED 显示验收（2026-10-27）

[OLED 实测](oled-test.md) 已确认中文显示、BOOT 播放、播放后唤醒及约 2.15 秒回到待机。OLED阶段固件哈希见 [oled-build-report.json](oled-build-report.json)，先前构建报告保留原阶段快照。显示状态由离线主任务更新，音频回调只发送事件；保留 Assets.Apply(false) 加载完整中文字库。电脑端组件见 [本机语音组件](../../server/NOTES.md)，完整板端网络问答尚未接入。

## 当前本地回应固件

历史阶段：唤醒后本地使用Breeze少女音回答“我在呀，你说！”，当时固定音量40；暂停识别、队列排空和300ms冷却后重新监听。板级 ut_wake_ack.ogg 只加入本板 EMBED_FILES，通过 wake_ack.h 引用，无需手改生成语言头或模型assets分区。覆盖目录须完整复制，build-voice.ps1会核对新增头与音频。当前构建与试听结果见 [回应记录](wake-ack-test.md)，OLED/喇叭旧报告保留各阶段快照。


新版应用2304416字节，已通过容量检查和四静态镜像校验。当前哈希见 [Breeze构建](breeze-playful-build-report.json)，两次串口周期和人工试听见 [Breeze实测](breeze-playful-test-report.json)。Huihui、OLED与喇叭旧报告保留为历史。
