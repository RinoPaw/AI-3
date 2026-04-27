# 牡丹智能对话系统

牡丹智能对话系统是一个本地运行的数字人对话演示项目。系统围绕“语音输入、知识检索、模型回复、语音播报、数字人界面展示”这一流程构建，适合用于课程展示、数字人交互原型和 RAG 对话系统学习。

项目主要在 Windows 环境下验证，核心代码使用 Python 编写，桌面界面基于 PySide6。

## 功能特性

- 语音识别：支持讯飞 RTASR 在线识别，也支持 Vosk 离线识别。
- 检索增强：使用 FAISS 向量检索，并结合关键词召回提升命中率。
- 大模型回复：通过智谱 API 生成回答。
- 语音播报：支持 Edge-TTS 在线播报和 pyttsx3 离线播报。
- 数字人界面：提供桌面端主界面，包含状态动画、对话气泡和交互按钮。
- 知识图谱页面：内置 Flask 页面，可独立展示本地知识图谱内容。

## 运行环境

- Windows 10 / 11
- Python 3.10+
- 可用麦克风与扬声器
- 必需：智谱 API Key
- 可选：讯飞开放平台 RTASR 配置、Vosk 离线识别模型

部分依赖（如 `PyAudio`、`faiss-cpu`、`torch`）在不同 Python 版本和系统环境下安装体验可能不同。建议优先使用 Python 3.10 或 3.11。

## 快速开始

1. 安装依赖：

```bash
pip install -r requirements.txt
```

也可以使用可编辑安装，让 `mudan` 包直接被当前环境识别：

```bash
pip install -e .
```

2. 创建本地配置文件：

```bash
copy .env.example .env
```

3. 编辑 `.env`，至少填写智谱 API Key：

```env
ZHIPU_API_KEY=your_zhipu_api_key
ZHIPU_MODEL=glm-4.5-flash
```

4. 如需使用讯飞在线语音识别，继续填写：

```env
XF_APPID=your_xf_appid
XF_API_KEY=your_xf_api_key
XF_API_SECRET=your_xf_api_secret
```

5. 启动桌面端：

```bash
python main.py
```

## 配置说明

项目会优先读取系统环境变量，也会自动加载项目根目录下的 `.env` 文件。

| 变量名 | 必填 | 说明 | 默认值 |
| --- | --- | --- | --- |
| `ZHIPU_API_KEY` | 是 | 智谱 API Key | 空 |
| `ZHIPU_MODEL` | 否 | 智谱模型名 | `glm-4.5-flash` |
| `XF_APPID` | 否 | 讯飞 RTASR 应用 ID | 空 |
| `XF_API_KEY` | 否 | 讯飞 RTASR API Key | 空 |
| `XF_API_SECRET` | 否 | 讯飞 RTASR API Secret | 空 |
| `XF_API_CONFIGS_JSON` | 否 | 多个讯飞账号配置，优先级高于单账号配置 | 空 |
| `VOSK_MODEL_PATH` | 否 | Vosk 离线语音识别模型路径 | `models/vosk-model-cn-0.22` |
| `EMBEDDING_MODEL_PATH` | 否 | 向量模型路径 | `models/embedding/BAAI/bge-large-zh-v1___5` |
| `FAISS_INDEX_PATH` | 否 | FAISS 索引文件路径 | `data/faiss_data/faiss_index.index` |
| `FAISS_DATA_PATH` | 否 | FAISS 元数据路径 | `data/faiss_data/faiss_data.json` |
| `FAISS_KEYWORD_PATH` | 否 | 关键词数据路径 | `data/faiss_data/my_keywords.json` |
| `AUDIO_HELLO_PATH` | 否 | 问候提示音路径 | `assets/audio/hello.mp3` |
| `FRAME_DIR_IDLE` | 否 | 待机动画帧目录 | `assets/animations/idle/0` |
| `HTML_PATH` | 否 | 知识图谱页面路径 | `web/heritage/templates/index.html` |

多讯飞账号配置示例：

```env
XF_API_CONFIGS_JSON=[{"APPID":"xxx","APIKey":"xxx","APISecret":"xxx"}]
```

`.env` 文件只用于本地运行，不应提交到仓库。

## 项目结构

```text
panda_mudan/
├── main.py                 # 项目根目录启动器
├── src/mudan/              # 核心 Python 包
│   ├── app.py              # 桌面端启动逻辑
│   ├── main_window.py      # PySide6 主界面
│   ├── config.py           # 配置与路径解析
│   ├── dialog_service.py   # 对话、模型调用与语音播报
│   ├── speech_controller.py# 语音识别流程控制
│   ├── vector_store.py     # FAISS 向量检索
│   └── video.py            # 数字人动画帧加载
├── assets/                 # 本地素材资源
│   ├── audio/              # 提示音频与生成音频
│   ├── icons/              # 界面图标和背景图
│   └── animations/         # 数字人动画帧与视频资源
├── data/                   # 检索数据、索引元数据和辅助文本
│   └── faiss_data/
│       ├── faiss_data.json       # 已提交：FAISS 对应文本数据
│       ├── my_keywords.json      # 已提交：关键词数据
│       └── faiss_index.index     # 未上传 GitHub：需手动下载或重新生成
├── models/                 # 未上传 GitHub：需手动下载本地模型文件
├── web/
│   ├── heritage/           # 知识图谱 Flask 页面
│   └── front/              # Web 前端展示资源
├── scripts/                # 测试脚本与工具脚本
├── .env.example            # 配置模板，已提交
├── .env                    # 未上传 GitHub：本地复制 .env.example 后填写
├── requirements.txt
└── README.MD
```

根目录下的 `say.py`、`say_say.py`、`faiss_db.py` 是旧模块名兼容入口，新代码优先使用 `src/mudan/` 下的模块。

需要手动准备的运行资源：

- `models/`：未上传 GitHub，需要从“资源下载”中的 models 链接下载，或自行准备同名模型目录。
- `data/faiss_data/faiss_index.index`：未上传 GitHub，需要从 data 资源包补回，或用现有检索数据重新生成。
- `.env`：不会上传 GitHub，需要从 `.env.example` 复制后填写本地 API Key。
- `.venv/`、`logs/`、`__pycache__/` 等运行产物不会上传，也不需要手动下载。

## 常用命令

启动桌面端：

```bash
python main.py
```

如果已经执行过 `pip install -e .`，也可以使用命令行入口：

```bash
mudan
```

单独启动知识图谱页面：

```bash
python web/heritage/app.py
```

验证核心模块语法：

```bash
python -m py_compile main.py src/mudan/*.py scripts/test_faiss.py
```

运行 FAISS 查询 smoke test：

```bash
python scripts/test_faiss.py
```

## 资源下载

模型、索引、音频和动画素材体积较大，仓库中可能不包含完整资源。缺失资源时，可按需下载并放回对应目录。

- 项目整体：<https://pan.baidu.com/s/1wKuYYoeXhD80HnuSkbSl6w>（提取码：`h54t`）
- models -> `models/`：<https://pan.baidu.com/s/15ZyH0jYMjHNLNI5aHrFuNQ>（提取码：`41mp`）
- data -> `data/`：<https://pan.baidu.com/s/1ccoQmU1BSTbK_wJVYe5hCw>（提取码：`y3ke`）
- audio -> `assets/audio/`：<https://pan.baidu.com/s/1TVteiziRqByfiQcEVKt1sw>（提取码：`k8au`）
- heritage -> `web/heritage/`：<https://pan.baidu.com/s/1md2ykPZXhQ9WBt66qrs6Fg>（提取码：`y9hv`）
- icon -> `assets/icons/`：<https://pan.baidu.com/s/1E69fO_b9Gp7ohXYnUOKzCQ>（提取码：`saz2`）
- process -> `assets/animations/`：<https://pan.baidu.com/s/1zQyRXYG6JfvfzVDprm96cQ>（提取码：`wsv6`）
- utils -> `scripts/tools/` 与 `assets/audio/sovice_question/`：<https://pan.baidu.com/s/1pRgEfW88VZ_UVfZ-DQU3jQ>（提取码：`7b9k`）
- web_front -> `web/front/`：<https://pan.baidu.com/s/12q_thQlc4D848W8BuU2OHQ>（提取码：`j7f4`）

## 常见问题

### 启动提示 `ZHIPU_API_KEY` 未配置

检查 `.env` 是否位于项目根目录，变量名是否为 `ZHIPU_API_KEY`，以及 Key 是否已经填写。

### 出现 `websocket ... fin=1 opcode=8 ... goodbye`

这通常表示 WebSocket 收到了正常关闭帧，不一定代表程序异常。若语音识别功能可正常使用，可以先忽略这类日志。

### 已联网但没有使用讯飞在线识别

检查 `XF_APPID`、`XF_API_KEY`、`XF_API_SECRET` 是否填写完整。未配置讯飞时，系统会尝试使用 Vosk 离线识别。

### 离线识别无法启动

确认 `VOSK_MODEL_PATH` 指向的模型目录存在。默认路径为 `models/vosk-model-cn-0.22`。

### 检索结果为空或命中较少

确认 `data/faiss_data/` 下的索引和元数据文件存在，并确认向量模型路径可用。索引缺失时需要先重新构建检索数据。

## 安全说明

- 不要提交 `.env` 或任何真实 API Key。
- 如果密钥曾出现在公开仓库历史中，建议立即到服务商后台轮换。
- 大模型、语音识别和 TTS 服务可能产生调用费用，请以对应服务商说明为准。
