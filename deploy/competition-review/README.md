# 综合管廊评审环境

此部署使用生产 Django 配置、独立 PostgreSQL、数据库共享限流和单个 Agent 工作进程。只导入告警 1234 的 38 条脱敏观测、FLAME-05、对应工单及 5 条工单状态记录。数据时间保持原样，报文与观测的内部标识替换为回放别名，页面标明历史实测回放。登录账号为 `reviewer@example.invalid`，仅具有查看者权限。密钥与评审密码按私有凭据保管。

## 容器初始化

1. 把冻结工作树及实际 V24 unified GLB 放在 Linux 主机。Git LFS 指针不能用来初始化。评审项目与实物项目分开部署。
2. 在仓库外创建权限为 700 的私有目录。为内部 PostgreSQL 生成密钥和证书，例如 `openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj /CN=db -keyout server.key -out server.crt`。放在私有 TLS 子目录下。
3. 在仓库外创建权限为 600 的评审 env，填写 `REVIEW_HOST`（固定 IPv4，无协议和端口）、`REVIEW_TLS_DIR`（TLS 绝对路径）、`REVIEW_DJANGO_SECRET`、`REVIEW_INTERNAL_TOKEN`、`REVIEW_DB_PASSWORD`、`APP_COMMIT_SHA` 及私有的 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_MODEL`。前三类随机凭据用 `openssl rand -hex 32` 分别生成。DeepSeek 密钥仅存服务端。
4. 在仓库根目录执行下列命令。评审密码由负责人用私有方式保存，提交时填比赛平台专用字段。

```bash
review() { docker compose --env-file /path/to/private/review.env -f deploy/competition-review/compose.yml "$@"; }
review config --quiet
review build api web
review run --rm api python manage.py migrate --noinput
review run --rm api python manage.py createcachetable
read -rs -p 'Reviewer password: ' COMPETITION_REVIEW_PASSWORD; printf '\n'
export COMPETITION_REVIEW_PASSWORD
review run --rm -e COMPETITION_REVIEW_PASSWORD \
  -v "$PWD/deploy/competition-review/p5-1234.json:/review/p5.json:ro" \
  -v "$PWD/frontend/public/models/utility-tunnel-v24-unified.glb:/review/model.glb:ro" \
  api python manage.py seed_competition_review /review/p5.json /review/model.glb
unset COMPETITION_REVIEW_PASSWORD
review up -d
```

## 固定 IPv4 的 HTTPS

只对公网开放 80/443，SSH 按实际管理来源限制。Web 容器绑定主机回环 18080。用 Nginx 对外反代，先启用示例的 80 端口部分并创建 `/var/www/review-acme`。用 Certbot 5.4 或更新版签发 IP 证书，取证书后启用示例的 443 部分和 WebSocket 映射。续签成功后执行 `nginx -t && systemctl reload nginx`，设置自动续签并做试运行。证书以 IP 校验，浏览器必须通过正常信任链验证。

```bash
sudo certbot certonly --preferred-profile shortlived --webroot \
  --webroot-path /var/www/review-acme --ip-address REVIEW_IPV4
```

IP 证书寿命约 6 天。保持公网 IP 和 HTTP 校验路径可用。官方平台是否接受纯 IP HTTPS 地址须实填确认。

## 外网验收

手机流量和另一外网分别访问 `https://REVIEW_IPV4/agent-workbench`。真实登录后检查三维加载、P5 状态和缺项、从告警 1234 发起三 Agent、关联工单复核。核对历史来源、同一告警、38 条观测和关联工单。对工单写入、设备控制、注册及管理入口分别验证拒绝。失败时保留运行状态，使用工作台重试原快照；保留已验收的历史材料供评审说明。评审结束后撤销评审密码与模型密钥，留存脱敏材料和验收记录。
