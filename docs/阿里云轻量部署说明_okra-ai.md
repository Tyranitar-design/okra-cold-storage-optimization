# 阿里云轻量部署说明：okra-ai.top

日期：2026-06-06

## 部署目标

把秋葵冷库优化 MIS 和 FastAPI 证据接口部署到阿里云轻量服务器，先用于展示：

- MIS Vue 前端：`/app`
- FastAPI API：`/api/v1/...`
- Agent v2 只读证据问答
- Optuna AI warm start 报告展示
- AI-Benders/cut ranking 机制展示
- 高德天气后端刷新接口

本云端展示版不运行 Gurobi、Optuna 正式实验或深度学习训练。

## 当前服务器信息

- 系统：Ubuntu 24.04
- 公网 IP：`106.14.181.83`
- 配置：2 核 / 2GB / 40GB
- 推荐先验证：`http://106.14.181.83/app`

## 安全提醒

- 不要把服务器密码写入项目文件。
- 部署完成后建议在阿里云控制台或服务器内修改一次密码。
- 后续正式公开域名访问时，建议启用 HTTPS。

## 阿里云控制台准备

1. 在轻量服务器防火墙中放行：
   - TCP `22`：SSH
   - TCP `80`：Nginx HTTP
   - TCP `8014`：FastAPI 临时直连验证（可选；当前公网展示已走 Nginx 80 端口）
2. 域名 `okra-ai.top` 当前可先不绑定；先用 IP 验证。
3. 如果要使用中国大陆服务器 + 域名正式访问，需要完成 ICP 备案/接入备案。

## 上传部署包

本地生成的部署包路径：

```text
D:\秋葵冷库优化项目\deploy\okra-cloud-deploy.tar.gz
```

如需重新生成部署包，先在本机 PowerShell 执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_cloud_deploy_package.ps1
```

该脚本会把云端展示必需的 `src/`、`data/`、`results/`、`docs/`、`frontend-vue/dist/`、部署脚本与轻量依赖清单打入压缩包；不要手工把整个项目目录递归复制到 `deploy/okra-cloud-deploy/`，否则容易把历史 staging 目录再次套进去。

可选上传方式：

### 方式 A：阿里云 Workbench 上传

1. 打开阿里云轻量服务器“远程连接”。
2. 使用 Workbench 的文件上传功能，将 `okra-cloud-deploy.tar.gz` 上传到服务器 `/tmp/`。

### 方式 B：本机 scp 上传

在本机 PowerShell 中运行：

```powershell
scp D:\秋葵冷库优化项目\deploy\okra-cloud-deploy.tar.gz root@106.14.181.83:/tmp/
```

然后按提示输入服务器密码。

## 服务器执行命令

在阿里云远程终端执行：

```bash
sudo mkdir -p /opt/okra-cold-storage/current
sudo tar -xzf /tmp/okra-cloud-deploy.tar.gz -C /opt/okra-cold-storage/current
cd /opt/okra-cold-storage/current
sudo bash deploy/install_or_update_okra.sh
```

完成后检查：

```bash
systemctl status okra-mis --no-pager
curl http://127.0.0.1:8014/health
curl http://127.0.0.1:8014/api/v1/experiments/ai-warmstart-report
```

浏览器访问：

```text
http://106.14.181.83/app
```

## 域名解析

如果要把 `okra-ai.top` 指向服务器：

| 主机记录 | 类型 | 记录值 |
|---|---|---|
| `@` | A | `106.14.181.83` |
| `www` | A | `106.14.181.83` |
| `api` | A | `106.14.181.83` |

DNS 生效后可访问：

- `http://okra-ai.top/app`
- `http://www.okra-ai.top/app`
- `http://api.okra-ai.top/api/v1/agent/chat`

## 移动端后端地址

部署成功后，Android App 的 Agent 页可填写：

```text
http://106.14.181.83/api/v1
```

域名解析成功后可填写：

```text
http://api.okra-ai.top/api/v1
```

后续开启 HTTPS 后，再改为：

```text
https://api.okra-ai.top/api/v1
```

## 常用排查命令

```bash
systemctl status okra-mis --no-pager
journalctl -u okra-mis -n 80 --no-pager
ss -lntp | grep 8014
curl http://127.0.0.1:8014/health
nginx -t
systemctl status nginx --no-pager
```

## 当前部署边界

- 云端 API 读取现有证据文件和报告，不运行求解器。
- 无数据库时走文件 fallback，不影响展示。
- 高德天气刷新需要在服务器环境变量里配置 `OKRA_AMAP_WEB_SERVICE_KEY`；未配置时天气页仍可显示部署包内置快照。
- HTTPS 与备案作为下一阶段处理。
