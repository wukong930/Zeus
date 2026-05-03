# Zeus Vercel 部署指南

仓库已推送到：https://github.com/wukong930/Zeus

## 方法一：Vercel Dashboard 导入（推荐）

1. 访问 https://vercel.com/new
2. 选择 **Import Git Repository** → 选择 `wukong930/Zeus`
3. **关键配置**：
   - Framework Preset: **Next.js**（自动识别）
   - Root Directory: **`frontend`** ← 必须设置
   - Build Command: `next build`（默认）
   - Output Directory: `.next`（默认）
4. 点击 **Deploy**

部署完成后会得到 `https://zeus-<random>.vercel.app` 域名。后续每次 `git push` 会自动重新部署。

## 方法二：CLI 部署（适合本地）

在你自己的终端（不是 Claude Code 沙盒）：

```bash
cd /Users/ninoo/Zeus/frontend
vercel login                    # 浏览器登录
vercel link                     # 关联项目（首次）
vercel --prod                   # 部署到生产
```

CLI 会问几个问题：
- Set up and deploy? → **Y**
- Which scope? → 你的账号（wukong930）
- Link to existing project? → **N**（首次部署）
- Project name? → **zeus** 或自定义
- Directory? → 直接回车（`./`，因为已 cd 到 frontend）
- Override settings? → **N**

后续 `git push` 不会自动触发 Vercel——除非你执行了"Connect Git Repository"。

## 方法三：Connect Git Repository 实现自动部署

CLI 部署成功后：

```bash
vercel git connect
```

之后 `git push` 会自动触发 Vercel 部署。

## 环境变量

当前前端仍可使用 `src/data/mock.ts` 独立运行。Phase 0 已加入 Python 后端骨架，如需联调 API 代理可配置：

- `NEXT_PUBLIC_API_URL` — Python FastAPI 地址
- `BACKEND_INTERNAL_URL` — Next.js rewrite 在服务端访问后端的地址

本地 Docker Compose 默认会把 `/api/*` 从 Next.js 代理到 `http://backend:8000/api/*`。

## 验证部署

部署成功后，访问 URL 应该看到：
1. 1.5 秒 Boot Sequence 启动动画
2. Command Center 首页（个性化欢迎条 + Causal Web 缩略 + 板块热力图 + 持仓概览）
3. 左侧导航栏（深翠色 Logo + 11 个页面）
4. 顶部 Heartbeat Bar（绿色心跳点）
5. 右下角 AI Companion 按钮（橙色脉动）
6. 按 `⌘K` 打开命令面板

## 路由清单

| 路径 | 页面 |
|------|------|
| `/` | Command Center |
| `/alerts` | Alerts |
| `/trade-plans` | Trade Plans |
| `/portfolio` | Portfolio Map |
| `/causal-web` | **Causal Web**（标志性页面） |
| `/industry` | Industry Lens |
| `/sectors` | Sectors |
| `/future-lab` | Future Lab |
| `/forge` | Strategy Forge |
| `/notebook` | Notebook |
| `/analytics` | Analytics（含推荐归因 + 校准 + Drift） |
| `/settings` | Settings |
