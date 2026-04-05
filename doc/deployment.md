# FunClip 服务器部署文档

> 记录 FunClip 在生产服务器上的部署目录结构和启动方式。

## 服务器信息

| 项目 | 值 |
|------|------|
| IP | 34.21.190.240 |
| 域名 | https://funclip.agentpit.io |
| 主机名 | agent1005 |
| 用户 | a1 |
| SSH 密钥 | ~/.ssh/id_rsa_google_longterm |
| 操作系统 | Debian 12 (bookworm) x86_64 |
| 规格 | 4 vCPU / 32 GB RAM / 99 GB 磁盘 |
| Python | 3.11.2 (venv: /opt/funclip/venv) |

## SSH 连接

```bash
ssh -i ~/.ssh/id_rsa_google_longterm a1@34.21.190.240
```

## 部署目录结构

```
/opt/funclip/                    # 项目根目录
├── .env                         # 环境变量 (ONE_API 配置)
├── .gitignore
├── LICENSE
├── README.md
├── README_zh.md
├── requirements.txt             # Python 依赖
├── funclip.pid                  # 进程 PID 文件
├── funclip.log                  # 运行日志
├── venv/                        # Python 虚拟环境
├── docs/                        # 文档目录
├── font/                        # 字体文件
└── FunClip/                     # 核心代码目录
    ├── __init__.py
    ├── launch.py                # 主启动文件 (Gradio 应用)
    ├── videoclipper.py          # 视频剪辑核心逻辑
    ├── introduction.py          # Gradio 页面介绍文本
    ├── llm/                     # LLM 调用模块 (Gemini API)
    ├── utils/                   # 工具函数
    └── test/                    # 测试文件
```

## 环境变量 (.env)

```bash
export ONE_API_BASE_URL=http://104.197.139.51:3000/v1
export ONE_API_KEY=sk-xxx
export ONE_API_GEMINI_MODEL=gemini-3-flash-preview
```

## 服务架构

```
客户端 → Nginx (80/443) → Gradio 应用 (127.0.0.1:7860)
```

### Nginx 配置

- 配置文件: `/etc/nginx/sites-enabled/funclip.agentpit.io`
- SSL: Let's Encrypt 证书 (certbot 自动续期)
- 证书路径: `/etc/letsencrypt/live/funclip.agentpit.io/`
- 反向代理: `proxy_pass http://127.0.0.1:7860`
- WebSocket 支持: `/queue/` 路径配置了 WebSocket 升级 (Gradio 需要)
- 上传限制: `client_max_body_size 500M`
- HTTP 自动跳转 HTTPS

## 启动方式

FunClip 通过 **nohup 后台运行** Gradio 应用，无 systemd/supervisor 管理。

### 启动命令

```bash
cd /opt/funclip
source venv/bin/activate
nohup python3 FunClip/launch.py --listen --port 7860 > funclip.log 2>&1 &
echo $! > funclip.pid
```

### 关键参数

- `--listen`: 监听所有网络接口 (0.0.0.0)
- `--port 7860`: Gradio 服务端口
- 其他可选参数: `--lang zh` (语言), `--share` (Gradio 公共链接)

### 停止服务

```bash
kill $(cat /opt/funclip/funclip.pid)
```

### 重启服务

```bash
cd /opt/funclip
kill $(cat funclip.pid 2>/dev/null) 2>/dev/null
sleep 2
source venv/bin/activate
nohup python3 FunClip/launch.py --listen --port 7860 > funclip.log 2>&1 &
echo $! > funclip.pid
```

## 依赖说明

### requirements.txt

```
librosa
soundfile
scikit-learn>=1.3.2
moviepy==1.0.3
numpy==1.26.4
gradio
openai
dashscope
```

### 主要已安装包

- gradio 6.10.0 — Web UI 框架
- moviepy 1.0.3 — 视频处理
- librosa 0.11.0 — 音频处理
- google-generativeai 0.8.6 — Gemini LLM 调用
- openai 2.30.0 — OpenAI 兼容 API 调用
- scikit-learn 1.8.0 — 机器学习工具
- numpy 1.26.4 — 数值计算

## 快速部署（更新代码）

```bash
# 1. 本地打包
cd /Users/a1/work/FunClip
tar czf /tmp/funclip-deploy.tar.gz \
  --exclude=.git --exclude=__pycache__ --exclude=.DS_Store \
  --exclude=venv --exclude=doc --exclude=.vscode \
  --exclude=.agentpit --exclude=.specstory \
  funclip/ requirements.txt

# 2. 上传
scp -i ~/.ssh/id_rsa_google_longterm /tmp/funclip-deploy.tar.gz a1@34.21.190.240:/tmp/

# 3. 部署并重启
ssh -i ~/.ssh/id_rsa_google_longterm a1@34.21.190.240 << 'EOF'
cd /opt/funclip
tar xzf /tmp/funclip-deploy.tar.gz -C FunClip/ --strip-components=1
rm /tmp/funclip-deploy.tar.gz
source venv/bin/activate
pip install -r requirements.txt
kill $(cat funclip.pid 2>/dev/null) 2>/dev/null
sleep 2
nohup python3 FunClip/launch.py --listen --port 7860 > funclip.log 2>&1 &
echo $! > funclip.pid
sleep 3
curl -sf http://127.0.0.1:7860 && echo " 部署成功" || echo " 部署失败"
EOF
```

## 常用运维命令

```bash
SSH="ssh -i ~/.ssh/id_rsa_google_longterm a1@34.21.190.240"

# 查看服务状态
$SSH "ps aux | grep launch.py | grep -v grep"

# 查看日志
$SSH "tail -50 /opt/funclip/funclip.log"

# 查看 Nginx 日志
$SSH "sudo tail -50 /var/log/nginx/error.log"

# 重载 Nginx 配置
$SSH "sudo nginx -t && sudo systemctl reload nginx"

# 健康检查
$SSH "curl -sf http://127.0.0.1:7860"
```

## 注意事项

1. **进程管理**: 当前使用 nohup 后台运行，服务器重启后需手动启动服务
2. **不要覆盖 .env**: 包含生产环境 API 密钥
3. **不要覆盖 venv/**: 服务器已安装完整依赖
4. **日志文件**: funclip.log 会持续增长，需定期清理
5. **本地代码目录映射**: 本地 `funclip/` → 服务器 `/opt/funclip/FunClip/`
