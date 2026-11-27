# AI-viewport
# 本地 AI 聊天后端

一个基于 FastAPI 的本地 AI 聊天后端服务，支持多连接配置管理、代理设置、连通性测试，以及兼容 OpenAI 格式的聊天接口转发。前端页面由项目根目录的 `index.html` 提供。

## 功能特性

- 🔌 **多连接管理**：可保存多个 AI 服务连接（endpoint / API Key / 模型 / 代理 / 自定义请求头），随时切换激活连接
- 🧪 **连通性测试**：一键测试连接，自动探测 `/models` 接口，失败时回退探测聊天接口，并返回耗时、HTTP 状态、可用模型列表
- 🌐 **代理支持**：每个连接可单独指定 HTTP/HTTPS 代理，也可直连；已隔离系统代理环境变量，避免相互污染
- 💬 **聊天转发**：`/api/chat` 兼容 OpenAI Chat Completions 格式，支持指定模型与 temperature
- 🖥️ **内置前端**：访问根路径 `/` 自动加载 `index.html` 管理界面
- 🔒 **密钥脱敏**：连接列表接口返回脱敏后的 API Key，不直接暴露完整密钥

## 技术栈

- Python 3.9+
- FastAPI + Uvicorn
- Pydantic
- requests
- python-dotenv
