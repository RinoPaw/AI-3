# 牡丹智能对话系统

基于 Python 的数字人对话系统，集成了语音识别、RAG 检索、LLM 回复和语音播报能力。

## 功能概览
- 语音输入：在线讯飞 RTASR / 离线 Vosk 双模式
- 检索增强：FAISS 向量检索 + 关键词召回
- 模型回复：智谱 API
- 语音播报：在线 Edge-TTS + 离线 pyttsx3
- 界面形态：桌面端主界面 + 网页知识图谱页面

## 3 分钟快速开始
1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 配置环境变量
```bash
copy .env.example .env
```
编辑 `.env`，至少填写：
- `ZHIPU_API_KEY`
- `XF_APPID`
- `XF_API_KEY`
- `XF_API_SECRET`（建议）

3. 启动
```bash
python main.py
```

## 项目结构（重构后）
```text
panda_mudan/
├── main.py                 # 程序入口
├── main_window.py          # 主界面
├── config.py               # 配置中心（环境变量优先）
├── dialog_service.py       # 对话与TTS核心
├── speech_controller.py    # 语音识别与对话流程控制
├── vector_store.py         # FAISS向量检索
├── heritage/
│   ├── app.py
│   └── templates/index.html
├── web_front/              # 前端页面资源
├── data/                   # 检索数据
├── models/                 # 本地模型（建议本地存放，不入库）
├── process/                # 动画帧/视频资源
├── audio/                  # 提示音频
├── icon/                   # 图标资源
└── requirements.txt
```

兼容说明：
- `say.py`、`say_say.py`、`faiss_db.py` 为兼容包装文件，内部已转发到新模块。

## 运行环境
- Python 3.10+
- Windows（当前主要在 Windows 上验证）

## 配置说明（.env）
项目已改为环境变量配置，`config.py` 会优先读取系统环境变量，并自动尝试加载项目根目录 `.env`。

常用变量如下：

| 变量名 | 必填 | 说明 | 默认值 |
| --- | --- | --- | --- |
| `ZHIPU_API_KEY` | 是 | 智谱 API Key | 空 |
| `ZHIPU_MODEL` | 否 | 智谱模型名 | `glm-4.5-flash` |
| `XF_APPID` | 建议 | 讯飞 RTASR 应用 ID | 空 |
| `XF_API_KEY` | 建议 | 讯飞 RTASR API Key | 空 |
| `XF_API_SECRET` | 建议 | 讯飞 RTASR API Secret | 空 |
| `XF_API_CONFIGS_JSON` | 否 | 多账号 JSON 配置（优先级高于单账号） | 空 |
| `HTML_PATH` | 否 | 知识图谱页面路径 | `heritage/templates/index.html` |

备注：
- 若未配置讯飞在线识别，系统会在联网场景下自动回退到离线识别。
- `.env` 已在 `.gitignore` 中忽略。

## 知识图谱页面
- 主界面会通过 `HTML_PATH` 打开本地页面。
- 也可单独运行：
```bash
python heritage/app.py
```

## 常见问题

### 1) `websocket ... fin=1 opcode=8 ... - goodbye`
通常是 WebSocket 收到正常关闭帧（1000），不一定是业务错误，可优先关注功能是否正常。

### 2) 启动提示 `ZHIPU_API_KEY` 未配置
检查 `.env` 是否填写、是否与 `main.py` 同目录，以及变量名是否拼写正确。

### 3) 已联网但走了离线识别
通常是讯飞环境变量未配置完整（`XF_APPID/XF_API_KEY`）。

### 4) FAISS 检索异常或命中少
先确认 `data/faiss_data/*` 与 `models/embedding/*` 路径存在；必要时重新构建索引。

## 开发与提交建议
- 不要提交真实密钥（`.env`、云服务凭据）。
- 模型和大体积资源建议本地存放，不纳入仓库历史。
- 提交前建议自检：
```bash
python -m py_compile main.py main_window.py config.py dialog_service.py speech_controller.py vector_store.py
```

## 资源下载（按需）
- 项目整体：<https://pan.baidu.com/s/1wKuYYoeXhD80HnuSkbSl6w>（提取码：`h54t`）
- models：<https://pan.baidu.com/s/15ZyH0jYMjHNLNI5aHrFuNQ>（提取码：`41mp`）
- data：<https://pan.baidu.com/s/1ccoQmU1BSTbK_wJVYe5hCw>（提取码：`y3ke`）
- audio：<https://pan.baidu.com/s/1TVteiziRqByfiQcEVKt1sw>（提取码：`k8au`）
- heritage：<https://pan.baidu.com/s/1md2ykPZXhQ9WBt66qrs6Fg>（提取码：`y9hv`）
- icon：<https://pan.baidu.com/s/1E69fO_b9Gp7ohXYnUOKzCQ>（提取码：`saz2`）
- process：<https://pan.baidu.com/s/1zQyRXYG6JfvfzVDprm96cQ>（提取码：`wsv6`）
- utils：<https://pan.baidu.com/s/1pRgEfW88VZ_UVfZ-DQU3jQ>（提取码：`7b9k`）
- web_front：<https://pan.baidu.com/s/12q_thQlc4D848W8BuU2OHQ>（提取码：`j7f4`）

## 安全提醒
- 如果密钥曾出现在仓库历史，建议在服务商后台立即轮换。
