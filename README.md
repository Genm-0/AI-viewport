# AI-viewport

> 一个基于 FastAPI 的本地 AI 聊天后端服务，支持多连接配置管理、代理设置、连通性测试，以及兼容 OpenAI 格式的聊天接口转发。

## ✨ 功能特性

- 🔌 **多连接管理**：可保存多个 AI 服务连接（endpoint / API Key / 模型 / 代理 / 自定义请求头），随时切换激活连接
- 🧪 **连通性测试**：一键测试连接，自动探测 `/models` 接口，失败时回退探测聊天接口，并返回耗时、HTTP 状态、可用模型列表
- 🌐 **代理支持**：每个连接可单独指定 HTTP/HTTPS 代理，也可直连；已隔离系统代理环境变量，避免相互污染
- 💬 **聊天转发**：`/api/chat` 兼容 OpenAI Chat Completions 格式，支持指定模型与 `temperature`
- 🖥️ **内置前端**：访问根路径 `/` 自动加载 `index.html` 管理界面
- 🔒 **密钥脱敏**：连接列表接口返回脱敏后的 API Key，不直接暴露完整密钥

## 🛠️ 技术栈

- **核心框架**：Python 3.9+, FastAPI, Uvicorn
- **数据校验**：Pydantic
- **HTTP 客户端**：requests
- **配置管理**：python-dotenv

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Genm-0/AI-viewport.git
cd AI-viewport
```

### 2. 创建虚拟环境并安装依赖

首先创建并激活虚拟环境：

**Windows:**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

然后安装依赖：
```bash
pip install -r requirements.txt
```

### 3. 启动服务

默认监听 `127.0.0.1:5050`：

```bash
python main.py
```

**自定义主机和端口：**
你可以通过环境变量覆盖默认设置：

```bash
# 示例：监听所有地址，端口 8000
HOST=0.0.0.0 PORT=8000 python main.py
```

启动成功后，在浏览器中访问 `http://127.0.0.1:5050/` 即可打开管理界面。

## 📸 界面预览

<img width="1911" height="1078" alt="AI-viewport 管理界面" src="https://github.com/user-attachments/assets/2603688a-c479-4f2a-b25a-e12b88795b54" />

---
