<p align="center">
  <img src="assets/logo.png" alt="AIRAG Logo" width="128" height="114">
</p>

<h1 align="center">AIRAG — 智能截图解析悬浮窗工具</h1>

<p align="center">
  <b>截屏 → AI 解析 → 悬浮窗即时显示结果</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/UI-PyQt6-green?logo=qt" alt="PyQt6">
  <img src="https://img.shields.io/badge/AI-LangGraph-orange" alt="LangGraph">
  <img src="https://img.shields.io/badge/VLM-豆包VL-red" alt="豆包VL">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
</p>

---

## 🎯 这是什么？

**AIRAG**（AI Screen Agent）是一个 Windows 桌面效率工具。按下 `Ctrl+D` 截取屏幕任意区域，多模态大模型（豆包 VL）即刻分析图片内容，答案以**流式打字**效果显示在透明悬浮窗上。支持多轮追问，就像和一个能"看见"你屏幕的 AI 对话。

### 典型场景

- 📊 截取表格/图表 → "帮我分析这张图的数据趋势"
- 🐛 截取报错信息 → "这个错误怎么解决？"
- 📄 截取文档段落 → "帮我翻译/总结这段文字"
- 💻 截取代码片段 → "这段代码有什么问题？"
- 🎨 截取设计稿 → "给出 HTML/CSS 实现建议"

---

## ✨ 功能特性

| 模块 | 说明 |
|------|------|
| 🔍 **智能截图** | 全屏半透明遮罩 + 鼠标拖拽选区域 + 8 锚点精细拉伸调整 |
| 🧠 **多模态 AI** | 基于 LangGraph 状态机编排，图片 + 文字混合输入，豆包 VL 解析 |
| 💬 **流式输出** | 结果逐字显示，体验顺畅，无需等待完整响应 |
| 🪟 **透明悬浮窗** | 无边框、置顶、可拖拽移动 + 四边四角缩放，半透明深色背景 |
| 🔄 **多轮对话** | 上下文自动管理，可在结果窗内追问，AI 记住之前的截图和对话 |
| ✂️ **Token 裁剪** | 自动滑动窗口裁剪历史，超过 1 轮的旧图片从上下文剔除，节省 Token |
| 📝 **Markdown 渲染** | 代码块、列表、表格等格式美美展示 |
| 💾 **上下文持久化** | 对话历史保存到本地 JSON，重启程序可继续对话 |
| 🔑 **API Key 管理** | 图形界面配置豆包 API Key，安全存储在本地配置文件 |
| 📌 **系统托盘** | 最小化到托盘，右键菜单唤起截图、退出程序 |
| 📦 **打包成 exe** | 支持 PyInstaller 一键打包，无需安装 Python 环境 |

---

## 🏗️ 系统架构

```text
┌─────────────────────────────────────────────────┐
│                  PyQt6 GUI 层                     │
│  ┌──────────────┐ ┌──────────┐ ┌─────────────┐  │
│  │ CaptureWindow│ │InputDialog│ │ ResultWindow │  │
│  │  截图遮罩层   │ │  追问输入  │ │  透明悬浮窗   │  │
│  └──────┬───────┘ └────┬─────┘ └──────┬──────┘  │
│         │               │              │         │
├─────────┼───────────────┼──────────────┼─────────┤
│         ▼               ▼              ▼         │
│  ┌──────────────────────────────────────────┐   │
│  │       LangGraph AI 编排层                 │   │
│  │  trim_history ──▶ call_vlm ──▶ END       │   │
│  │     (裁剪历史)      (调用豆包VL)           │   │
│  └────────────────────┬─────────────────────┘   │
│                       │                         │
│         ┌─────────────▼─────────────┐           │
│         │    ChatDoubaoVL Client    │           │
│         │  (火山引擎方舟 API 调用)    │           │
│         └───────────────────────────┘           │
└─────────────────────────────────────────────────┘
```

**核心流程**：快捷键触发 → 截图选区域 → 图片压缩转 Base64 → LangGraph 裁剪旧历史 → 拼装多模态消息 → 调用豆包 VL API → 流式文本逐字推送到悬浮窗

---

## 🚀 快速上手

### 1. 安装依赖

```bash
git clone https://github.com/zebinlu7-a11y/screen-flow-ai-agent.git
cd screen-flow-ai-agent
pip install -r requirements.txt
```

### 2. 配置 API Key

前往 [火山引擎方舟控制台](https://console.volcengine.com/ark) 获取 API Key，然后：

- **方式 A**：启动程序后在托盘右键 → "设置 API Key" 图形化配置
- **方式 B**：设置环境变量 `ARK_API_KEY=你的key`

### 3. 启动

```bash
python main.py
```

程序启动后出现在系统托盘，按 `Ctrl+D` 开始截图！

### 4. 快捷键 & 操作

| 操作 | 说明 |
|------|------|
| `Ctrl+D` | 触发截图 |
| 鼠标拖拽 | 在遮罩层上选取截图区域 |
| 拖动 8 个锚点 | 精细调整选区范围 |
| `Enter` | 确认截图（未选区则截全屏） |
| `Esc` | 取消截图 |
| 悬浮窗内输入 | 对上一次截图进行追问 |

---

## 📁 项目结构

```text
AIRAG/
├── main.py                 # 程序主入口：托盘、快捷键、信号串联
├── config.py               # 全局配置（快捷键、Token 上限、UI 参数）
├── build_exe.py            # PyInstaller 打包脚本
├── requirements.txt        # Python 依赖
│
├── agent/                  # LangGraph AI 编排模块
│   ├── state.py            # AgentState 状态类型定义
│   ├── graph.py            # 图拓扑：trim_history → call_vlm
│   └── llm_client.py       # 豆包 VL 适配的 LangChain LLM 客户端
│
├── gui/                    # PyQt6 UI 模块
│   ├── capture_window.py   # 全屏截图遮罩（拖拽、8 锚点拉伸）
│   ├── input_widget.py     # 追问输入弹窗
│   ├── result_window.py    # 透明悬浮结果窗（流式、Markdown、可缩放）
│   └── api_key_dialog.py   # API Key 配置对话框
│
├── utils/                  # 工具模块
│   ├── image_tool.py       # 图片压缩、QImage ↔ PIL、Base64 编码
│   ├── token_counter.py    # Token 估算 + 历史图片剥离
│   ├── context_store.py    # 对话上下文 JSON 持久化
│   └── api_key_manager.py  # API Key 本地安全存储
│
└── assets/
    └── logo.png            # 应用图标
```

---

## ⚙️ 配置说明

[config.py](config.py) 中可调整：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_HOTKEY` | `ctrl+d` | 全局截图快捷键 |
| `MAX_TURNS` | `5` | 最大保留对话轮数 |
| `MAX_TOKEN_ESTIMATE` | `8000` | 上下文 Token 上限 |
| `MAX_IMAGE_WIDTH/HEIGHT` | `1920 / 1080` | 图片压缩最大尺寸 |
| `JPEG_QUALITY` | `85` | 图片压缩质量 |
| `RESULT_WINDOW_OPACITY` | `0.92` | 结果窗透明度 |
| `RESULT_FONT_SIZE` | `13` | 结果窗字号 |

---

## 📦 打包为 exe

```bash
python build_exe.py
```

打包输出在 `dist/` 目录，可独立运行，无需 Python 环境。

---

## 🛠️ 技术栈

- **Python 3.9+**
- **PyQt6** — 桌面 GUI（透明窗口、截图遮罩、系统托盘）
- **LangGraph** — AI 对话状态机（多轮上下文管理 + 流式编排）
- **LangChain Core** — 多模态消息格式 (`HumanMessage` / `AIMessage`)
- **火山引擎豆包 VL** — 多模态大模型 API（通过 OpenAI 兼容接口）
- **Pillow** — 图片压缩、格式转换
- **keyboard** — 全局快捷键监听

---

## 📄 License

MIT © [zebinlu7-a11y](https://github.com/zebinlu7-a11y)

---

<p align="center">
  ⭐ 如果这个项目对你有用，欢迎点个 Star！
</p>
