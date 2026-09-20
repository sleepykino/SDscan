# SDscan — 多平台敏感信息检索系统

敏感信息监测系统，支持GitHub、道客巴巴等多个平台敏感信息监测，同时支持自定义新的搜索接口

> 仅用于授权范围内的安全自查与合规核查。

## 功能特性

- **5 种任务模板**
  - T1 关键词检索：多关键词逐平台轮询检索
  - T2 域名归集：梳理单位官方域名/子域名，自动归并 + 人工确认/驳回的域名清单
  - T3 附件排查：搜索引擎语法检索公开附件，下载并解析 PDF/DOCX/XLSX 后跑敏感规则
  - T4 风险页面核查：`inurl:admin / intitle:登录` 类语法核查管理入口、测试页面
  - T5 内容核查：`site:{domain}` 遍历页面，正文跑敏感规则库
- **13+ 内置平台**：百度、必应、360 搜索、GitHub、Gitee、CNNVD、FreeBuf、盘搜搜、百度文库、豆丁网、道客巴巴、语雀、CSDN；平台清单可增删改、启停，URL 模板/翻页/选择器/headers/Cookie 全部界面可配，附「测试」按钮即时验证
- **采集双通道**：httpx（api 型）/ Playwright Chromium（web 型：动态渲染、反检测注入、每结果页一张截图）
- **风控半自动处理**：触发验证码/封禁时 WebSocket 实时告警、只暂停当前平台，一键弹出有头浏览器人工过码，Cookie 自动回填后恢复
- **断点续跑**：每条「关键词 × 平台 × 页码」组合状态落库，任务中断后自动跳过已完成组合，单组合重试上限 3 次
- **敏感规则引擎**：内网信息/证件号码/联系方式/运维凭据/员工隐私/业务敏感词六类分级规则（正则），界面 CRUD，命中结果脱敏展示
- **结果管理**：统一九字段结果列表、多维筛选、截图预览、一键导出 Excel（含敏感命中分级列）
- **实时交互**：REST + WebSocket 推送进度、风控告警与终端式日志流

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · uvicorn · asyncio · SQLAlchemy 2.0（SQLite） |
| 采集 | httpx · Playwright Chromium · parsel（CSS/XPath） |
| 附件解析 | PyMuPDF（pdf）· python-docx（docx）· openpyxl（xlsx） |
| 前端 | Vue 3 · Element Plus · Vite · Pinia |
| 通信 | REST · WebSocket |

## 快速开始

### 1. 后端

```bash
cd backend

# 创建虚拟环境（run.py 会自动引导使用 .venv）
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt

# web 通道需要浏览器内核
python -m playwright install chromium

# 启动（默认 http://127.0.0.1:8000）
python run.py
```

启动时自动建库并播种默认平台、敏感规则与语法字典。

### 2. 前端（可选）

仓库不携带构建产物，直接用后端 API 或自行构建：

```bash
cd frontend
npm install
npm run build
```

构建生成的 `frontend/dist/` 由后端**单端口托管**（含 history 回退），构建后重启后端即可直接访问 `http://127.0.0.1:8000`。

开发模式可另起 Vite：`npm run dev`。

### 3. 访问

浏览器打开 `http://127.0.0.1:8000`，接口文档见 `/docs`。

## 配置

- 环境变量：`SDSCAN_HOST`（默认 127.0.0.1）、`SDSCAN_PORT`（默认 8000）
- 运行时产物统一落在根目录 `data/`：SQLite 数据库、结果页截图、下载附件、`settings.json`（请求间隔、翻页数、超时、UA、GitHub Token 等，界面「全局设置」可改）

## 目录结构

```
SDscan/
├── backend/
│   ├── app/
│   │   ├── api/          # REST 端点（平台/任务/结果/命中/规则/附件/域名/设置）
│   │   ├── core/
│   │   │   ├── engine/   # httpx 与 Playwright 双通道采集、Cookie、风控
│   │   │   ├── scheduler # 任务调度：组合状态机、断点续跑、暂停/取消
│   │   │   └── ...       # 模板后处理、敏感引擎、附件解析
│   │   ├── ws/           # WebSocket 事件推送
│   │   └── seed.py       # 默认平台/规则/语法字典幂等播种
│   ├── tests/            # 离线 smoke 与本机 E2E
│   └── run.py            # 启动入口（自动引导虚拟环境）
├── frontend/             # Vue 3 + Element Plus
└── data/                 # 运行时数据（不入库）
```

## 测试

```bash
cd backend
python tests/smoke_offline.py   # 离线单元冒烟（URL 构造、选择器、规则引擎等）
python tests/e2e_local.py       # 本机 fixture 站点端到端（无外网依赖）
```

