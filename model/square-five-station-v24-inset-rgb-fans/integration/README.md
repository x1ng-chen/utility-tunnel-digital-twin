# 风机联动参考实现

`fan-motion.mjs` 从本轮本地测试通过的 `frontend/src/utils/fanMotion.ts` 编译为 ES2022，保留相同逻辑；类型被移除，Three.js 依赖指向仓库 `frontend/node_modules`，不额外引入运行框架。来源 SHA256 见 `reference-provenance.json`。

仓库根目录执行：

```sh
npm --prefix frontend ci
node model/square-five-station-v24-inset-rgb-fans/integration/verify-fan-motion.mjs
```

接入网页时，在 GLTFLoader 成功加载后调用 `createFanAnimator(gltf.scene)`，并在已有渲染循环每帧执行 `animator.update({telemetry,bindings,source:'api',offline:false}, Date.now(), deltaSeconds)`。卸载模型前执行 `animator.dispose()`。不要再创建一套重复的 requestAnimationFrame。

每台风机需要它自己的在线 `HardwareBinding` 与新鲜 `rotational.speed/rpm`、`supply.voltage/V`。灯只看供电，叶片只看转速。采样质量必须为 good，过期或断线显示未知，示例/演示来源不会被当作实物上报。

RGB Mesh 使用 `userData.fanRgb=true`、`fanAssetCode`、`fanRgbColor` 和 `fanRgbOnIntensity`。业务告警的材质克隆、重着色及逐帧发光脉冲应跳过这些 RGB Mesh，否则会覆盖独立供电亮灭。RGB 材质由联动器克隆并在 dispose 时恢复、释放。

平台轮询还需持续刷新最新绑定/心跳，并单独保留 FAN-01/FAN-02 的采样窗口；不能只取全局最新若干条后让大量传感器挤掉风机数据。不能用浏览器时间伪造新的心跳。

本目录为模型配套参考；本次模型上传不会自动部署前端、切换活动模型或修改运行台账。
