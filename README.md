# 招投标智能体集成系统

面向国家电网等招投标场景的文档智能体平台：上传招标文件压缩包后，自动完成**解压 → 解析 → 信息抽取 → 标包识别 → 知识库匹配 → 投标 DOCX 生成 → 合规检查**，把原本数小时的人工编标流程压缩到分钟级。

系统把 tender-extract、BiaoShu-SKILL 与易标（OpenBidKit_Yibiao）三条外部能力整合进同一条流水线；**不配置任何外部服务时，规则抽取 + 内置生成器可完全离线运行**。

## 目录

- [核心能力](#核心能力)
- [技术栈](#技术栈)
- [架构与流水线](#架构与流水线)
- [快速开始](#快速开始)
- [外部服务与模型配置](#外部服务与模型配置)
- [知识库组织](#知识库组织)
- [投标文件生成规则](#投标文件生成规则)
- [API 一览](#api-一览)
- [测试](#测试)
- [Docker 部署](#docker-部署)
- [目录结构](#目录结构)
- [常见问题](#常见问题)

## 核心能力

### 1. 文档预处理

- 多层嵌套压缩包：`.zip / .rar / .7z / .tar.gz`，支持 GBK 文件名、密码字典、递归深度限制、路径穿越防护
- 多格式转 Markdown：PDF / DOCX / DOC / TXT / Markdown / XLSX
- 图片与扫描件可选 PaddleOCR 识别，形成统一的 Markdown 与结构化数据层

### 2. 招标信息抽取

- 输出 26 个核心字段，并保留原文证据定位
- 优先调用 tender-extract HTTP 服务；服务不可用时自动降级为内置规则引擎
- 低置信字段通过 DeepSeek / OpenAI / Ollama 兼容接口复核，支持多模型配置

### 3. 标包与产品解析

- 识别 `包X_完整招标文件_<编码>.zip`、`包X_技术规范书_<编码>.zip` 结构，提取项目名称、项目编号、分标名称、分标编号、包名称、包号、技术规范编码
- 同名包号跨分标场景按分标隔离，避免不同分标的包与产品串用
- 按包归组技术规范书，输出中文结构化 JSON

### 4. 标书预览

- 招标关键信息按条目展示：资质要求拆分为"产品资质 / 企业资质 / 投标人资格要求"，长段文本整理为 1./2./3. 条目
- 技术规范书原格式原文预览，支持 PDF 预览与源文件下载
- 技术评分规则、专用资格要求按"分标名称 + 分标编号 + 包号"精准匹配后展示
- 一级目录任务中心与"国网投标专项"任务中心数据隔离，互不干扰

### 5. 知识库（RAG）

- 双知识库：`国网专属/` + `通用/`，另设 `共享/` 存放公司基础资料
- Obsidian 兼容：Markdown + Frontmatter + `[[WikiLink]]` + `#标签`
- SQLite 关键词检索 + 可选 ChromaDB 向量检索
- 国网投标专用知识映射规则：章节标题 → 知识库目录/标签，可在界面维护、预览、重置

### 6. 投标文件生成

- 以 `backend/templates/投标格式.docx` 为样式基座，替换该文件即可套用企业自有投标格式
- 原文版式保留：复制招标文件「商务部分 / 技术部分（单独成册）」正文，表格、合并单元格、图片、页面设置原样保留
- 知识库内容注入到对应章节的「知识库参考内容」下，正文宋体小四、1.5 倍行距
- 生成后保留中间 Markdown，便于排查与二次加工

### 7. 合规检查

8 类检查：签字盖章、项目名称、报价范围、资质完整性、时间有效性、章节完整性、查重、保证金，输出可视化合规报告。

### 8. 控制台

一级目录：工作台、任务中心、标书预览、知识库、合规检查、国网投标专项、系统设置。

「国网投标专项」为二级工作台：上传标书、标书预览、任务中心、知识映射规则。

### 9. 桌面端

`frontend/electron/` 提供 Electron 壳，`npm run dist` 可打包 macOS / Windows / Linux 桌面应用。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12、FastAPI、SQLAlchemy、Celery、Redis、PyJWT |
| 文档处理 | python-docx、lxml、PyMuPDF、openpyxl、PaddleOCR、LibreOffice |
| 检索与模型 | SQLite 关键词检索、ChromaDB 向量检索、BGE 中文嵌入、DeepSeek / OpenAI / Ollama |
| 前端 | React 19、TypeScript、Vite、lucide-react、Electron |
| 部署 | Docker Compose、Nginx |

## 架构与流水线

```text
上传压缩包 / 单文件
        │
        ▼
┌───────────────────┐
│ 1. 预处理 preprocess│  递归解压 → 格式转换 → OCR → Markdown / 结构化数据
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 2. 抽取 extract     │  tender-extract 优先 → 规则引擎降级 → LLM 复核 26 字段
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 3. 标包解析 packages│  分标 / 包 / 产品 / 技术规范编码 归类
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 4. 生成 generate    │  投标格式模板 + 原文版式克隆 + 知识库注入 → DOCX
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 5. 检查 check       │  8 类合规检查 → 报告
└───────────────────┘
```

任务编排与降级逻辑集中在 `backend/app/pipeline.py`，各阶段可单独通过 API 触发，也支持上传后自动跑全流程（`/api/preprocess?auto_run=true`）。

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- （可选）LibreOffice：技术规范书 PDF 预览与 .doc 变体转换
- （可选）PaddleOCR：扫描件与图片文字识别

### 后端

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # 按需修改配置
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

- API 文档：http://127.0.0.1:8080/docs
- 健康检查：http://127.0.0.1:8080/api/health

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

> 首次登录后请立即修改默认密码；生产环境必须替换 `BID_SYSTEM_SECRET_KEY`。

### 桌面端

```bash
cd frontend
npm run dev:electron   # 开发模式
npm run dist           # 打包安装包（输出到 frontend/release/）
```

## 外部服务与模型配置

所有配置均可通过 `backend/.env` 或环境变量覆盖，完整模板见 [`backend/.env.example`](backend/.env.example)。

### tender-extract（信息抽取服务）

| 配置项 | 说明 |
| --- | --- |
| `TENDER_EXTRACT_URL` | 服务地址，默认 `http://localhost:8000` |
| `TENDER_EXTRACT_TIMEOUT` | 请求超时（秒） |
| `TENDER_EXTRACT_API_KEY` | 服务鉴权密钥（可选） |
| `TENDER_LLM_PROVIDER` / `TENDER_LLM_MODEL` / `TENDER_LLM_API_KEY` / `TENDER_LLM_BASE_URL` | 交给 tender-extract 使用的模型配置 |

未配置或调用失败时，系统自动降级到内置规则引擎，不影响主流程。

### LLM 复核（多模型）

```bash
LLM_PROVIDER=deepseek        # none / deepseek / openai / ollama
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o-mini

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

系统设置界面支持同时勾选多个模型，并配合 PaddleOCR 组成多模态识别链路；任一模型不可用时自动切换下一个。

### BiaoShu-SKILL（标书生成）

```bash
BIAOSHU_SKILL_PATH=/path/to/BiaoShu-SKILL-main/BiaoShu-writer-pro
BIAOSHU_OUTPUT_DIR=./data/generated
BIAOSHU_TIMEOUT=300
```

未配置时使用内置 DOCX 生成器。

### 向量检索

```bash
USE_VECTOR_SEARCH=false                  # 开启后使用 ChromaDB
CHROMA_PERSIST_DIR=./data/chroma_db
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
```

### 其他开源项目

| 项目 | 对接方式 | 配置项 |
| --- | --- | --- |
| tender-extract | HTTP `POST /v1/extract` | `TENDER_EXTRACT_URL` |
| BiaoShu-SKILL | 子进程调用 `scripts/bid_writer_pipeline.py` | `BIAOSHU_SKILL_PATH` |
| OpenBidKit_Yibiao | 二次开发 UI 或 Electron 桥接 | `window.yibiaoBridge.registerSkill` |

## 知识库组织

知识库位于 `backend/knowledge_base/`，Obsidian 可直接打开该目录。

```text
knowledge_base/
├── 国网专属/          # 国网投标专用资料，国网投标专项只从这里取
├── 通用/              # 其他行业 / 通用投标资料
├── 共享/              # 公司基础资料，国网与通用共用
│   ├── 01_企业资质/    # 营业执照、认证证书、许可证
│   ├── 02_历史标书/    # 历史标书与业绩
│   ├── 03_行业政策/    # 政策与规范
│   ├── 04_公司介绍/    # 公司简介、团队、售后
│   ├── 05_投标模板/    # 标书模板
│   └── 06_产品资料/    # 产品手册、技术方案、检测报告
└── _system_generated/ # 系统自动生成内容
```

笔记规范：

- Frontmatter 建议维护 `tags`、`industry`、`doc_type`、`valid_until` 等字段
- 正文支持 `[[WikiLink]]` 与 `#标签`
- `*sync-conflict*` 冲突文件会被自动忽略
- 知识映射规则决定"哪个章节去哪个目录/标签取内容"，可在「国网投标专项 → 知识映射规则」中维护并试检索

## 投标文件生成规则

生成阶段以 `backend/templates/投标格式.docx` 为样式与编号来源，当前规则：

1. **原文结构优先**：保留招标文件原有的章节文字与顺序，不重命名、不合并标题
2. **中文序号标题不编号**：`三、技术文件`、`（一）技术偏差表`、`（二）专项投标文件` 这类自带中文序号的段落只保留加粗格式，不套用 Word 自动编号，避免出现双重编号
3. **正文标题统一一级**：其余带大纲级别的标题统一为「一级标题」
4. **分节重新计数**：每个「（X）」分节生成独立编号实例并设置 `startOverride=1`，因此 `（二）` 下的第一个标题重新显示为 1，而不是延续上一节
5. **空标题清理**：文本为空但套了标题样式的段落会被自动删除，避免出现空编号条目
6. **知识库内容格式**：注入内容追加为「知识库参考内容」，正文宋体小四、1.5 倍行距，不参与标题编号

更换企业模板时，只需替换 `backend/templates/投标格式.docx` 并确认其中的 Heading 1–9 样式与编号定义。

## API 一览

### 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录，返回 JWT |
| GET | `/api/auth/me` | 当前用户信息 |

### 任务与流水线

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/preprocess?auto_run=true` | 上传压缩包/单文件，可选自动跑全流程 |
| GET | `/api/tasks` | 任务列表（支持按来源过滤） |
| GET | `/api/tasks/{id}` | 任务详情（抽取结果、合规报告） |
| POST | `/api/tasks/{id}/run` | 触发指定阶段或全流程 |
| DELETE | `/api/tasks/{id}` | 删除任务 |
| POST | `/api/extract` | 信息抽取 |
| POST | `/api/generate` | 标书生成 |
| POST | `/api/check` | 合规检查 |
| GET | `/api/download/{id}` | 下载生成的 DOCX |
| WS | `/ws/task/{id}?token=...` | 任务进度推送 |

### 标包与投标文件

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/tasks/{id}/packages` | 标包/产品结构化数据 |
| POST | `/api/tasks/{id}/packages/parse` | 重新解析标包 |
| POST | `/api/tasks/{id}/packages/{package_no}/generate` | 按包 + 产品生成投标文件 |
| GET | `/api/tasks/{id}/package-bid?path=...` | 下载生成的投标文件 |
| GET | `/api/tasks/{id}/package-file?path=...` | 读取技术规范书内容 |
| GET | `/api/tasks/{id}/package-file/preview?path=...` | 技术规范书 PDF 预览 |

### 知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST/PUT/DELETE | `/api/kb/documents` | 知识库文档管理 |
| POST | `/api/kb/upload` | 上传知识库文件 |
| GET | `/api/kb/search?q=...` | 关键词/向量检索 |
| GET/POST/DELETE | `/api/kb/types` | 知识库分类管理 |
| GET | `/api/kb-files/tree` | Obsidian 目录树 |
| GET/POST | `/api/kb-files/note` | 读取 / 保存笔记 |
| GET/POST | `/api/kb-files/search` | 全库检索 |
| POST | `/api/kb-files/reindex` | 重建索引 |

### 国网投标专项

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/bid-special/chapter-rules` | 读取知识映射规则 |
| PUT | `/api/bid-special/chapter-rules` | 保存知识映射规则 |
| POST | `/api/bid-special/chapter-rules/reset` | 重置为默认规则 |
| POST | `/api/bid-special/chapter-rules/preview` | 试检索预览 |

### 系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET / PUT | `/api/settings` | 读取 / 更新系统配置 |

## 测试

```bash
cd backend
.venv/bin/python -m pytest -q
```

当前覆盖 49 个用例，涉及：嵌套压缩包预处理、26 字段规则抽取、标包解析、引用解析、DOCX 生成与标题层级/编号、知识库检索与注入、合规检查、登录鉴权、上传到下载的端到端流水线。

前端类型检查与构建：

```bash
cd frontend
npm run build
```

## Docker 部署

```bash
# 基础服务：Redis / PostgreSQL / API / Worker
docker compose up -d redis postgres api worker

# 如需 tender-extract 与 Nginx
docker compose --profile extract --profile web up -d
```

生产环境注意事项：

- 替换 `BID_SYSTEM_SECRET_KEY`，关闭 `BID_SYSTEM_DEBUG`
- 启用 HTTPS，并在 `CORS_ORIGINS` 中限定来源
- 容器内需包含 LibreOffice 才能使用 PDF 预览
- 定期清理 `data/tasks` 下的历史任务文件

## 目录结构

```text
bid-agent/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── pipeline.py             # 任务编排与降级
│   │   ├── config.py               # 配置项
│   │   ├── api/                    # REST + WebSocket 路由
│   │   ├── kb_integration/         # Obsidian 知识库网关与映射规则
│   │   └── modules/                # 预处理 / 抽取 / 标包 / 生成 / 合规
│   ├── knowledge_base/             # Obsidian 兼容知识库
│   ├── templates/投标格式.docx      # 投标文件样式基座
│   └── tests/                      # pytest 用例
├── frontend/
│   ├── src/pages/                  # 工作台、任务中心、标书预览、知识库、合规、国网投标专项、设置
│   ├── src/components/
│   └── electron/                   # 桌面壳
├── deploy/nginx.conf.example
├── Dockerfile.api
├── Dockerfile.worker
└── docker-compose.yml
```

## 常见问题

**Q：没有 tender-extract / BiaoShu-SKILL 能用吗？**
能。系统会自动降级为内置规则抽取与内置 DOCX 生成器，全流程可离线跑通。

**Q：技术规范书预览打不开或显示异常？**
预览依赖 LibreOffice 把 `.doc/.docx` 转 PDF。安装后系统会自动识别 `/Applications/LibreOffice.app`（macOS），未安装时回退到 Microsoft Word / Pages。

**Q：RAR 解压后中文文件名乱码？**
依赖系统 `bsdtar`（macOS/Linux 自带），可正确还原 GBK 文件名；也可安装 `rarfile` + `unrar` 作为备选路径。

**Q：同一个"包01"在多个分标下会串吗？**
不会。标包数据按分标维度隔离，生成时用"分标名称 + 分标编号 + 包号"三者同时定位。

**Q：生成稿里出现空编号或空标题？**
生成阶段会自动删除"空文本 + 标题样式"的段落。若仍出现，请确认使用的是最新版本并重新生成。

**Q：系统设置里 tender-extract / BiaoShu-SKILL 显示 not configured 有影响吗？**
没有硬性影响，只是走内置能力。配置后可以显著提升抽取精度与生成质量。

## 说明

- 本仓库为企业投标提效工具，未声明开源许可证；如需对外开源请补充 `LICENSE`
- 公司资料类知识库内容（公司简介、业绩、设备清单等）建议保留在本地，不要提交到公开仓库
- 生成结果仍需人工复核，尤其是金额、资质有效期、签章等关键信息
