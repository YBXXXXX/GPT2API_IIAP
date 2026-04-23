# GPT2API_IIAP

ChatGPT Web 图像生成网关。将 ChatGPT Web 的图像生成能力封装为 OpenAI 兼容的 API，支持多账号智能调度、全局排队和后台管理。

## 特性

- **OpenAI 兼容 API** — `/v1/images/generations` 返回标准格式
- **多账号调度** — 额度最多的账号优先，单账号最多 2 并发
- **全局 FIFO 队列** — 请求先进先出，前端实时显示排队位置
- **一键导入** — 支持 sub2api JSON 格式批量导入账号
- **管理面板** — 独立 `/panel` 页面，密码保护，支持刷新/删除账号
- **SQLite 存储** — 无需额外数据库，账号、额度、调用记录本地持久化

## 架构

```
前端 (React SPA)          后端 (FastAPI)
   /ui  ──────────────►  公开 API
   /admin ────────────►  管理 API (需 Admin Token)
                          │
                          ▼
                    全局 FIFO Queue
                   (asyncio.Queue)
                          │
                          ▼
                Account 选择器 (额度优先)
                          │
                          ▼
              ChatGPT Web 协议层
       (bootstrap → chat-requirements → PoW
        → conversation → poll → download)
```

## 安装

```bash
git clone <repo>
cd GPT2API_IIAP

# 复制配置模板
cp .env.example .env
# 编辑 .env 填写你的 token

# 启动（自动创建虚拟环境、安装依赖）
./start.sh
```

## 配置 (.env)

```env
# 管理员密码（也是默认 API Key）
ADMIN_TOKEN=your-secure-password

# ChatGPT Web 凭证（用于自动导入一个默认账号）
OPENAI_ACCESS_TOKEN=eyJhbG...
OPENAI_SESSION_TOKEN=eyJhbG...

# 代理（如需翻墙）
UPSTREAM_PROXY=http://127.0.0.1:7897

# 监听地址
HOST=127.0.0.1
PORT=8787
```

## 使用

### 1. 导入账号

打开管理面板：http://127.0.0.1:8787/panel

- 输入 `ADMIN_TOKEN` 登录
- 切换到「导入账号」标签
- 粘贴 sub2api 导出的 JSON（或单个 `access_token`）
- 点击导入

### 2. 生成图片

打开前端页面：http://127.0.0.1:8787/ui

- 输入 Prompt，点击生成
- 等待队列处理，显示实时排队位置
- 生成完成后可下载 PNG

### 3. API 调用

```bash
curl -X POST http://127.0.0.1:8787/v1/images/generations \
  -H "content-type: application/json" \
  -d '{"prompt":"一只猫","model":"gpt-image-1","n":1}'
# 返回: {"request_id":"...","status":"queued"}

# 轮询结果
curl http://127.0.0.1:8787/v1/queue/result/$REQUEST_ID
```

## API 列表

| 端点 | 方法 | 说明 |
|------|------|------|
| `/healthz` | GET | 健康检查 |
| `/ui` | GET | 图片生成前端页面 |
| `/panel` | GET | 管理面板（需密码） |
| `/v1/models` | GET | 模型列表 |
| `/v1/images/generations` | POST | 提交生成请求（认证可选） |
| `/v1/queue/status` | GET | 当前队列状态 |
| `/v1/queue/result/{id}` | GET | 查询生成结果 |
| `/admin/status` | GET | 管理状态（需认证） |
| `/admin/accounts` | GET | 账号列表 |
| `/admin/accounts/import-sub2api` | POST | 批量导入 sub2api JSON |
| `/admin/accounts/refresh` | POST | 刷新账号元数据 |
| `/admin/accounts` | DELETE | 删除账号 |

## 调度策略

1. **队列层** — 所有请求进入全局 `asyncio.Queue`，8 个 worker 并发消费
2. **账号选择** — 每次从可用账号中选 `quota_remaining` 最高的
3. **并发控制** — 每个账号默认最多 2 个并发请求（通过 `LocalRequestScheduler`）
4. **失败处理** — token 失效自动标记为 `invalid`，其他失败换下一个账号重试

## 注意事项

- **refresh_token**：已存储但不自动刷新。因为 OpenAI OAuth 的 `refresh_token_reused` 错误会导致同一账号在其他设备（如 codex 官方）掉线。如需刷新请手动在管理面板操作。
- **额度显示**：新导入的账号需要「刷新」一次才能从 `/backend-api/conversation/init` 获取真实额度。
- **NSFW / 拒绝**：如果 prompt 触发 ChatGPT 安全策略，会返回 `no file IDs found after polling` 错误。

## 目录结构

```
GPT2API_IIAP/
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── api_public.py     # 公开 API
│   ├── api_admin.py      # 管理 API
│   ├── service.py        # 业务逻辑（调度、认证）
│   ├── queue_manager.py  # 全局 FIFO 队列
│   ├── models.py         # Pydantic 模型
│   └── config.py         # 配置 (.env)
├── accounts/
│   └── importer.py       # 账号导入解析
├── scheduler/
│   ├── local_scheduler.py # 并发/节流控制
│   └── routing.py         # 账号选择策略
├── storage/
│   ├── control.py         # SQLite CRUD
│   └── migrations.py      # 建表 SQL
├── upstream/
│   └── chatgpt.py         # ChatGPT Web 协议实现
├── frontend/
│   ├── index.html         # 用户生成页面
│   ├── app.js             # 用户端 React
│   ├── admin.html         # 管理面板
│   └── admin.js           # 管理端 React
├── tests/
│   └── test_core.py       # 核心测试
├── start.sh               # 一键启动脚本
├── requirements.txt
└── .env
```

## License

MIT
