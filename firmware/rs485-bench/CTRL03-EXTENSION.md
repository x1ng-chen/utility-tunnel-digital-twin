# 增加3号从站：当前实施记录

2026-10-26。用户明确确认已拔掉4号板及S3，电脑现在只接3号板。COM5被复用，不能继续把它当成4号板；S3的COM3当前未枚举。

## 已完成

- 先读取3号UID，确认与此前4号不同；芯片ID0x414，Flash实读256KB。
- 完整备份3号原Flash到`artifacts/rs485-bench-20261026/ctrl03-COM5-before.bin`。
- 从站地址变为可配置的1～4，诊断寄存器布局及协议版本不变；新增地址3镜像，原运行4号镜像没有重新烧录。
- 3号9188字节镜像写入、工具校验和独立读回内容一致。ROM GO返回成功但首次运行采集无日志，等待用户BOOT0/BOOT1=0及物理RST；不能宣称3号启动已通过。
- S3双节点程序构建成功：按4、3交替轮询、每次间隔500ms；每节点独立累计成功、超时和畸形计数，响应头地址与寄存器身份均匹配才认定有效。双节点镜像尚未烧录，S3目前没有连接电脑。
- 两端协议启动自检扩展为9例，包括错地址/错寄存器身份的有效CRC回复拒绝。3号及新S3的真实执行结果仍待启动日志确认。

同轮随后：用户确认3号BOOT0/BOOT1均设为0并复位，COM5实读`CTRL03_BENCH selftest=PASS`，uptime15023/20031ms递增，requests/CRC/UART/溢出均0。3号正常启动及9项启动协议自检通过，见`artifacts/rs485-bench-20261026/ctrl03-boot-acceptance.json`。共享总线和新S3双从站执行仍未验证。

## 可复现构建

```powershell
cmake -S firmware/rs485-bench/stm32 -B firmware/rs485-bench/build/stm32-ctrl03 -G Ninja -DBENCH_SLAVE_ADDRESS=3
cmake --build firmware/rs485-bench/build/stm32-ctrl03
python -X utf8 -m platformio run --project-dir firmware/rs485-bench/s3 -e s3_gateway_bench_dual
```

镜像为`build/stm32-ctrl03/rs485_ctrl03_bench.bin`与`s3/.pio/build/s3_gateway_bench_dual/`各文件。烧录按当次实际枚举及用户确认的目标执行，不把COM5写死为3或4号。

## 接线目标，尚未确认实施

先确认3号启动，再断电加入模块：3号3V3/GND分别接自己485模块3V3/GND，PA2→TXD、PA3←RXD、NC悬空。沿此前已核对的所选模块命名，不套用于其他模块。

三设备主干为`网关 → 4号 → 3号`：从4号模块的A/B/GND向3号延伸同名三线，保留原网关到4号主干，不星型分叉、不闭环。3号是新末端，网关和3号接入终端，4号退出终端；滑块导通方向按原理图/断电测量确认，不能凭上下位置猜测。

接回S3 COM口、3号ISP口及4号供电后，重新枚举串口。先核对S3芯片身份与已知记录，再更新双节点镜像；当前程序无执行器控制，不能直接宣称业务联动完成。主从正常读数、两个身份独立、单节点断线不拖累另一节点都需实测。

## 版本追溯

修改前的单从站源码和状态保存在`artifacts/rs485-bench-20261026/ctrl03-extension-baseline/`。PlatformIO切换环境后清理了原单从站构建目录，因此从此前独立校验过的S3 Flash读回文件恢复并归档其三段镜像，逐段原SHA256匹配；运行中S3固件未因此改变。当前`build-status.json`将原S3镜像指向该归档，保留先前构建路径供追溯。

4号及原S3的历史自检/通信结论继续属于原镜像。新源码、构建通过、3号烧录通过、3号启动和双从站总线通过是不同阶段，分别记录。
