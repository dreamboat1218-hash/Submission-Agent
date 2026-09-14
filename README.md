# 招投标智能体集成系统

将 tender-extract、BiaoShu-SKILL 与易标工作流整合为一条自动化流水线：
上传招标文件 → 递归解压与格式转换 → 26 字段信息抽取 → 自动生成 DOCX 投标文件 → 合规检查。

## 功能

- 多层嵌套压缩包预处理：`.zip / .rar / .7z / .tar.gz`，支持 GBK 文件名、密码字典、深度限制、路径穿越防护
- PDF / DOCX / TXT / Markdown / XLSX 转 Markdown，图片可选 PaddleOCR
- 信息抽取：优先调用 tender-extract HTTP 服务；不可用时自动降级为内置规则引擎，输出 26 个核心字段及证据定位
- 精准模式：低置信字段通过 DeepSeek / OpenAI / Ollama 兼容接口复核
- 标书生成：优先调用 BiaoShu-SKILL `bid_writer_pipeline.py`；不可用时使用内置 DOCX 生成器，保留中间 Markdown
- 格式感知模板：解析阶段识别招标文件中的“投标文件格式”（如商务文件/技术文件/价格文件/投标函/偏差表等章节与模板），生成阶段按识别结果动态编排标书章节
- 原文版式保留：识别到“商务部分/技术部分（单独成册）”时，直接复制招标文件原 DOCX 的对应正文，表格、合并单元格、图片与页面设置原样保留，不做 Markdown 重建
- 标包解析模块：从 `包X_完整招标文件_<编码>.zip` / `包X_技术规范书_<编码>.zip` 中按包提取项目名称、项目编号、分标名称、分标编号、包名称、包号、技术规范编码，并把每个包内的技术规范书文件归组输出中文结构化 JSON（接口：`GET/POST /api/tasks/{id}/packages`）
- 知识库：企业资质、历史标书、项目案例、模板库、FAQ；SQLite 关键词检索 + 可选 ChromaDB 向量检索
- 合规检查：签字盖章、项目名称、报价范围、资质完整性、时间有效性、章节完整性、查重、保证金 8 类检查
- Web 控制台：上传、任务进度（WebSocket）、抽取结果、标书预览与下载、知识库管理、合规报告、系统设置
- Electron 壳：`frontend/electron/`，可用 `npm run dist` 打包桌面端

## 快速启动（本地开发）

### 后端

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

API 文档：http://127.0.0.1:8080/docs

### 前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://127.0.0.1:5173 ，内置账号：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| admin | admin123 | 管理员 |
| auditor | audit123 | 审核员 |
| demo | demo123 | 普通用户 |

没有配置 tender-extract / BiaoShu-SKILL 时，系统会自动使用规则抽取和内置生成器，全流程离线可用。

> RAR 解压依赖系统自带的 `bsdtar`（macOS/Linux 均自带），可正确还原 GBK 中文文件名；
> 也可安装 `rarfile` + `unrar` 作为备选解压路径。

> 技术规范书 PDF 预览依赖 LibreOffice（推荐，支持 WPS 生成的 .doc 变体）；
> 未安装 LibreOffice 时回退到 Microsoft Word / Pages 自动转换。macOS 安装后系统会自动识别
> `/Applications/LibreOffice.app`。整体打包部署时请将 LibreOffice 一并包含。

## 对接三个开源项目

| 项目 | 对接方式 | 配置项 |
| --- | --- | --- |
| tender-extract | HTTP `POST /v1/extract` | `TENDER_EXTRACT_URL` |
| BiaoShu-SKILL | 子进程调用 `scripts/bid_writer_pipeline.py` | `BIAOSHU_SKILL_PATH` |
| OpenBidKit_Yibiao | 二次开发 UI 或 Electron 桥接 | `window.yibiaoBridge.registerSkill` |

```bash
# 示例：启用 BiaoShu-SKILL
BIAOSHU_SKILL_PATH=/Users/you/投标助手2/BiaoShu-SKILL-main/BiaoShu-writer-pro
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录，返回 JWT |
| POST | `/api/preprocess?auto_run=true` | 上传压缩包/单文件并可选自动跑全流程 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{id}` | 任务详情（含抽取 JSON、合规报告） |
| POST | `/api/tasks/{id}/run` | 触发全流程 |
| POST | `/api/extract` | 信息抽取 |
| POST | `/api/generate` | 标书生成 |
| POST | `/api/check` | 合规检查 |
| GET | `/api/download/{id}` | 下载 DOCX |
| GET/POST/PUT/DELETE | `/api/kb/...` | 知识库管理 |
| GET | `/api/kb/search?q=...` | 知识库检索 |
| WS | `/ws/task/{id}?token=...` | 任务进度推送 |

## Docker Compose

```bash
docker compose up -d redis postgres api worker
# 如需启动 tender-extract 与 Nginx
docker compose --profile extract --profile web up -d
```

环境变量模板见 [backend/.env.example](backend/.env.example)，生产部署请替换 `BID_SYSTEM_SECRET_KEY` 并启用 HTTPS。

## 测试

```bash
cd backend
.venv/bin/python -m pytest -q
```

覆盖：嵌套压缩包预处理、26 字段规则抽取、DOCX 生成、合规检查、登录、知识库、上传到下载的端到端流水线。

## 目录结构

```text
bid-agent/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口
│   │   ├── pipeline.py      # 任务编排与降级
│   │   ├── modules/         # 预处理/抽取/生成/知识库/合规
│   │   └── api/             # REST + WebSocket 路由
│   └── tests/
├── frontend/
│   ├── src/                 # React + TypeScript 控制台
│   └── electron/            # 桌面壳
├── deploy/nginx.conf.example
├── Dockerfile.api
├── Dockerfile.worker
└── docker-compose.yml
```
