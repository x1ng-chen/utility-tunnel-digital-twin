# GIS 设备位置模块

## 职责边界

GIS 总览使用 WGS84 经纬度显示开发板实物模块的地理位置与接入状态；“设备台账”负责运行检索和导出，“资产主数据”负责管理员维护设备身份、内部二维坐标与 WGS84 坐标。三个模块共享同一 `Asset` 数据，不重复维护业务状态。

## 当前实物口径

模块清单以项目计划书 V2.7 的实物盘点和 `firmware/stm32f103rct6` 当前固件为准：

| 硬件编号 | 软件资产 | 当前口径 |
| --- | --- | --- |
| H-01 | `CTRL-01` | STM32F103RCT6 主控，已验证 |
| H-02 | `LED-01` | RGB 灯带，待供电与时序验证 |
| H-03 | `DISP-01` | ST7735S TFT，PB4–PB9 软件 SPI，已验证 |
| H-04 | `SEEP-W01` | 水位 ADC，PC0/ADC1_IN10，已接入待标定 |
| H-05 | `MOIST-01` | 土壤湿度，仅作辅助展示 |
| H-06 | `ENV-01` | DHT11，PA1，约 2 秒采样，已验证 |
| H-07 | `VIB-01` | SW-420，PA4/EXTI4，固件已接入待实测 |
| H-08 | `BUZZ-01` | 有源蜂鸣器，电平与电压待确认 |
| H-09 | `RELAY-01` | 5V 继电器，触发电平待确认 |
| H-10 | `FAN-01` | 风扇与 IN-A/IN-B 驱动，电气及反馈待验证 |
| H-11 | `BT-01` | HC-05，可选调试链路 |
| H-25 | `PCB-01` | 洞洞板，非运行资产 |

未交付或未接入固件的计划传感器不会显示为在线，也不会生成虚假遥测。甲烷、CO、氧气、烟雾、ESP8266 和 MQTT 等仍按计划保留为后续接入项。

## 坐标真实性

未配置坐标的普通资产使用 `unassigned`；当前种子数据使用 `demo_anchor` 坐标源，仅用于验证 GIS 交互，页面会持续显示“非 GPS/非现场测绘”提示。正式现场坐标必须使用以下来源之一：

- `configured`：经审批的人工配置；
- `surveyed`：现场测绘；
- `gps`：定位设备采集。

数据库约束要求经纬度同时存在，纬度范围为 `[-90, 90]`，经度范围为 `[-180, 180]`。接口用数值返回坐标，前端再次验证有限数和 WGS84 范围后才创建标记。

## 底图配置

前端使用项目内锁定的 Leaflet 1.9.4，不依赖浏览器 CDN 脚本。开发环境默认使用 OpenStreetMap 公共瓦片并保留署名；生产环境必须按组织网络与供应商条款配置获批瓦片服务：

```dotenv
VITE_GIS_TILE_URL=https://tile-provider.example.com/{z}/{x}/{y}.png
VITE_GIS_ATTRIBUTION=Map data attribution required by provider
```

底图加载失败时，页面进入“降级”状态，资产数据、筛选和详情仍可使用。生产容量、缓存和服务等级不依赖 OpenStreetMap 公共开发瓦片。

## 数据模型与筛选

`Asset` 包含 `hardwareCode`、`integrationStatus`、`interface`、`capabilities`、`latitude`、`longitude`、`locationSource`、`installationNote`、`isActive` 和 `version`。`GET /api/assets/` 支持 `integrationStatus`、`hardwareCode`、`hasLocation=true|false` 与生命周期筛选，并保留原有搜索、状态、区域与分页参数。

管理员通过独立的“资产主数据”页面修改位置。服务端强制经纬度成对、WGS84 范围、坐标来源一致性以及平面 `x/y` 的 `0–100` 范围；更新必须携带版本号。已有活动告警或未结束工单时禁止停用资产，避免 GIS 标记消失后留下无法处置的业务记录。
