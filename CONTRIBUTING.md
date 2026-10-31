# 协作规范

## 开始前

先读[当前进度](docs/PROJECT_STATUS.md)和[文档导航](docs/README.md)。从最新`main`建立短分支，建议命名`feat/<topic>`、`fix/<topic>`、`docs/<topic>`。保留其他协作者未提交的内容，不使用强制推送或整目录覆盖解决冲突。

## 交付一个可审查的改动

1. 在Issue/PR说明具体问题、目标设备/页面、版本及验收范围。
2. 修改实现及受影响文档，维护采集编号、资产、模型和主控的显式映射。
3. 运行适合改动的检查，在PR记录命令、结果与未执行项。
4. CI通过后合并main。不要绕过失败门禁，也不要把模拟、桩测试或旧版本结果作为新实物验收。

## 检查入口

```powershell
npm ci --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
python backend/manage.py test --noinput
python -m unittest discover -s firmware/four-controller/tests -p 'test_*.py'
node tools/quality-scan.mjs
```

Python须使用已安装`backend/requirements.lock`的独立环境；测试运行`DJANGO_ENV=test`，禁用付费模型。固件构建见[发布说明](firmware/four-controller/RELEASE.md)，模型大文件先`git lfs pull`。CI/普通测试不得调用付费模型、下载本地大模型、烧录板卡或驱动真实执行器。

## 文件与凭据

- 源码按模块放置；临时日志、数据库、账号、Flash备份、`.env`和密钥留在被忽略的本地目录。
- Blend/GLB和已声明的模型资产使用Git LFS，保留冻结交付的原始字节与SHA清单。
- 业务固件与临时诊断明确分开。发布包必须标明目标、构建、Flash地址、大小、SHA256及实物验证状态；2号默认交付完整业务镜像。
- 历史模型和验收记录不批量删除；确认无引用和回退用途后再做有记录的清理。
- README只保留当前入口。新结果写入日期化记录，再更新`docs/PROJECT_STATUS.md`，避免连续在主页叠加相互矛盾的“最新”章节。

## 实物及模型结论

原始ADC不是标定浓度；回执不等于转动，转动不等于测速准确；告警恢复需要新鲜有效观测。发现问题请保留失败记录、来源、时间和构建标识，不将未知值写成正常或零值。
