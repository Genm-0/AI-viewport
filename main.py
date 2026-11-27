# main.py
# 安装依赖: pip install fastapi uvicorn requests python-dotenv

import os
import json
import uuid
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

load_dotenv()

# 清除系统代理环境变量（防止污染），每个连接按需自行指定
for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(key, None)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "connections.json")

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    connection_id: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)


class ConnectionInput(BaseModel):
    name: str
    endpoint: str
    api_key: str
    model: str
    request_proxy: Optional[str] = ""   # 例: http://127.0.0.1:7890，空表示直连
    extra_headers: Optional[Dict[str, str]] = {}


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    request_proxy: Optional[str] = None
    extra_headers: Optional[Dict[str, str]] = None


class TestConnectionRequest(BaseModel):
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    request_proxy: Optional[str] = None
    extra_headers: Optional[Dict[str, str]] = {}
    connection_id: Optional[str] = None


# ==================== 配置存储 ====================

def load_connections() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        return {"connections": {}, "active_id": None}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "connections" not in data:
                data = {"connections": {}, "active_id": None}
            return data
    except Exception as e:
        logger.error(f"读取配置失败: {e}")
        return {"connections": {}, "active_id": None}


def save_connections(data: Dict[str, Any]):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"写入配置失败: {e}")


# ==================== 应用 ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    data = load_connections()
    logger.info("=" * 50)
    logger.info("🚀 AI 聊天后端服务启动")
    logger.info(f"💾 配置文件: {CONFIG_FILE}")
    logger.info(f"📁 已保存连接数: {len(data['connections'])}")
    logger.info(f"🟢 当前激活: {data.get('active_id') or '无'}")
    logger.info("=" * 50)
    yield
    logger.info("👋 服务关闭")


app = FastAPI(title="本地AI聊天后端", version="1.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ==================== 工具函数 ====================

def build_headers(api_key: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    if extra:
        headers.update(extra)
    return headers


def get_models_url(endpoint: str) -> str:
    if "/chat/completions" in endpoint:
        return endpoint.replace("/chat/completions", "/models")
    return endpoint.rstrip("/") + "/models"


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]
class ProxyTLSAdapter(HTTPAdapter):
    """
    专门用于代理隧道的 adapter，放宽 TLS 校验，
    解决 Python OpenSSL 与 Clash 代理握手时的 SSLEOFError。
    """
    def __init__(self, *args, **kwargs):
        self.ssl_context = create_urllib3_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        # 关闭对代理隧道证书链的严格校验
        self.ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs['ssl_context'] = self.ssl_context
        return super().proxy_manager_for(*args, **kwargs)




def build_session(request_proxy: Optional[str] = None) -> requests.Session:
    """
    构造 requests.Session。
    - 有代理：显式设置 proxies，使用 requests 默认 TLS 栈（不挂自定义 adapter）。
    - 无代理：trust_env=False 直连，避免系统环境变量干扰。
    """
    session = requests.Session()
    if request_proxy and request_proxy.strip():
        proxy = request_proxy.strip()
        session.proxies = {"http": proxy, "https": proxy}
        session.trust_env = False  # 防止环境变量里的代理覆盖显式设置
    else:
        session.trust_env = False
    return session

def resolve_connection(connection_id: Optional[str] = None,
                       endpoint: Optional[str] = None,
                       api_key: Optional[str] = None,
                       request_proxy: Optional[str] = None,
                       extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    if connection_id:
        data = load_connections()
        conn = data["connections"].get(connection_id)
        if not conn:
            raise HTTPException(status_code=404, detail=f"配置 {connection_id} 不存在")
        return {
            "endpoint": conn["endpoint"],
            "api_key": conn["api_key"],
            "model": conn.get("model", ""),
            "request_proxy": conn.get("request_proxy", ""),
            "extra_headers": conn.get("extra_headers", {}),
            "name": conn.get("name", ""),
        }
    if not endpoint or not api_key:
        raise HTTPException(status_code=400, detail="必须提供 connection_id 或 endpoint+api_key")
    return {
        "endpoint": endpoint,
        "api_key": api_key,
        "model": "",
        "request_proxy": request_proxy or "",
        "extra_headers": extra_headers or {},
        "name": "临时连接",
    }

# ==================== 页面 ====================

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>index.html 未找到</h1>", status_code=404)


@app.get("/health")
async def health():
    data = load_connections()
    return {"status": "ok", "connection_count": len(data["connections"]), "active_id": data.get("active_id")}


# ==================== 连接配置 CRUD ====================

@app.get("/api/connections")
async def list_connections():
    data = load_connections()
    items = []
    for cid, c in data["connections"].items():
        items.append({
            "id": cid,
            "name": c.get("name", ""),
            "endpoint": c.get("endpoint", ""),
            "model": c.get("model", ""),
            "request_proxy": c.get("request_proxy", ""),
            "api_key_masked": mask_key(c.get("api_key", "")),
            "has_key": bool(c.get("api_key")),
            "is_active": cid == data.get("active_id"),
        })
    return {"connections": items, "active_id": data.get("active_id")}


@app.post("/api/connections")
async def create_connection(conn: ConnectionInput):
    data = load_connections()
    cid = str(uuid.uuid4())[:8]
    data["connections"][cid] = {
        "name": conn.name.strip() or f"连接-{cid}",
        "endpoint": conn.endpoint.strip(),
        "api_key": conn.api_key.strip(),
        "model": conn.model.strip(),
        "request_proxy": (conn.request_proxy or "").strip(),
        "extra_headers": conn.extra_headers or {},
    }
    if not data.get("active_id"):
        data["active_id"] = cid
    save_connections(data)
    logger.info(f"➕ 新增连接: {cid} ({data['connections'][cid]['name']}) proxy={data['connections'][cid]['request_proxy'] or '无'}")
    return {"id": cid, "connection": data["connections"][cid]}


@app.put("/api/connections/{cid}")
async def update_connection(cid: str, upd: ConnectionUpdate):
    data = load_connections()
    if cid not in data["connections"]:
        raise HTTPException(status_code=404, detail="配置不存在")
    c = data["connections"][cid]
    if upd.name is not None: c["name"] = upd.name.strip()
    if upd.endpoint is not None: c["endpoint"] = upd.endpoint.strip()
    if upd.api_key is not None and upd.api_key.strip(): c["api_key"] = upd.api_key.strip()
    if upd.model is not None: c["model"] = upd.model.strip()
    if upd.request_proxy is not None: c["request_proxy"] = upd.request_proxy.strip()
    if upd.extra_headers is not None: c["extra_headers"] = upd.extra_headers
    save_connections(data)
    logger.info(f"✏️ 更新连接: {cid}")
    return {"id": cid, "connection": c}


@app.delete("/api/connections/{cid}")
async def delete_connection(cid: str):
    data = load_connections()
    if cid not in data["connections"]:
        raise HTTPException(status_code=404, detail="配置不存在")
    del data["connections"][cid]
    if data.get("active_id") == cid:
        data["active_id"] = next(iter(data["connections"]), None)
    save_connections(data)
    return {"status": "ok", "active_id": data.get("active_id")}


@app.post("/api/connections/{cid}/activate")
async def activate_connection(cid: str):
    data = load_connections()
    if cid not in data["connections"]:
        raise HTTPException(status_code=404, detail="配置不存在")
    data["active_id"] = cid
    save_connections(data)
    logger.info(f"🟢 激活连接: {cid} ({data['connections'][cid]['name']})")
    return {"status": "ok", "active_id": cid}


# ==================== 测试连接 ====================

@app.post("/api/test-connection")
async def test_connection(req: TestConnectionRequest):
    try:
        conn = resolve_connection(req.connection_id, req.endpoint, req.api_key,
                                  req.request_proxy, req.extra_headers)
    except HTTPException as e:
        return {"connected": False, "error": e.detail}

    endpoint = conn["endpoint"]
    api_key = conn["api_key"]
    extra = conn["extra_headers"]
    proxy = conn["request_proxy"]

    if not endpoint or not api_key:
        return {"connected": False, "error": "API 地址或密钥为空"}

    models_url = get_models_url(endpoint)
    headers = build_headers(api_key, extra)
    result = {
        "connected": False, "models": [], "models_url": models_url,
        "endpoint": endpoint, "proxy": proxy or "无(直连)",
        "error": None, "http_status": None, "elapsed_ms": None,
    }
    import time
    start = time.time()
    session = build_session(proxy)

    try:
        resp = session.get(models_url, headers=headers, timeout=15)
        result["elapsed_ms"] = int((time.time() - start) * 1000)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            result["connected"] = True
            try:
                data = resp.json()
                raw = data.get("data", []) if isinstance(data, dict) else []
                if not raw and isinstance(data, list): raw = data
                ids = []
                for m in raw:
                    if isinstance(m, dict):
                        mid = m.get("id") or m.get("name") or m.get("model")
                        if mid: ids.append(mid)
                    elif isinstance(m, str):
                        ids.append(m)
                result["models"] = sorted(set(ids))
            except Exception as e:
                result["error"] = f"连接成功但解析模型列表失败: {e}"
        elif resp.status_code in (401, 403):
            result["error"] = f"认证失败 ({resp.status_code})，密钥可能无效"
        elif resp.status_code == 404:
            result["error"] = "/models 不存在(404)，尝试探测聊天接口..."
            try:
                probe = session.post(endpoint, headers=headers, json={
                    "model": conn.get("model") or "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1, "stream": False,
                }, timeout=20)
                if probe.status_code in (200, 400):
                    result["connected"] = True
                    result["error"] = "/models 不可用，但聊天接口连通"
                else:
                    result["error"] = f"聊天接口探测失败: HTTP {probe.status_code}"
            except Exception as e2:
                result["error"] = f"聊天接口探测异常: {e2}"
        else:
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.Timeout:
        result["elapsed_ms"] = int((time.time() - start) * 1000)
        result["error"] = "请求超时（15秒）"
    except requests.exceptions.ProxyError as e:
        result["elapsed_ms"] = int((time.time() - start) * 1000)
        result["error"] = f"代理错误: {e}（请检查代理地址是否可用，例如 {proxy or '未配置'}）"
    except requests.exceptions.ConnectionError as e:
        result["elapsed_ms"] = int((time.time() - start) * 1000)
        result["error"] = f"无法连接: {e}"
    except Exception as e:
        result["elapsed_ms"] = int((time.time() - start) * 1000)
        result["error"] = f"未知错误: {e}"

    return result


# ==================== 聊天 ====================

@app.post("/api/chat")
async def chat(request: ChatRequest):
    data = load_connections()
    cid = request.connection_id or data.get("active_id")
    if not cid:
        raise HTTPException(status_code=400, detail="没有可用的连接配置")
    conn = data["connections"].get(cid)
    if not conn:
        raise HTTPException(status_code=404, detail="连接配置不存在")

    model = request.model or conn.get("model", "")
    if not model:
        raise HTTPException(status_code=400, detail="未指定模型")

    payload = {
        "model": model,
        "messages": [m.dict() for m in request.messages],
        "temperature": request.temperature,
        "stream": False,
    }
    headers = build_headers(conn["api_key"], conn.get("extra_headers", {}))
    proxy = conn.get("request_proxy", "")

    logger.info(f"📤 [{conn.get('name', cid)}] {conn['endpoint']} | 模型 {model} | 代理 {proxy or '无'} | 消息 {len(payload['messages'])}")

    session = build_session(proxy)

    try:
        resp = session.post(conn["endpoint"], headers=headers, json=payload, timeout=120)
        if not resp.ok:
            try:
                err = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                err = resp.text or resp.reason
            raise HTTPException(status_code=resp.status_code, detail=f"上游API错误: {err}")
        return JSONResponse(content=resp.json())
    except requests.exceptions.ProxyError as e:
        raise HTTPException(status_code=502, detail=f"代理连接失败: {e}（代理: {proxy}）")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="上游API请求超时")
    except requests.exceptions.ConnectionError as e:
        raise HTTPException(status_code=502, detail=f"无法连接到AI服务: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("未知错误")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {e}")


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5050"))
    uvicorn.run("main:app", host=host, port=port, reload=True, log_level="info")