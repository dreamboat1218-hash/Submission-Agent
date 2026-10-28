"""桌面端启动入口。

被 PyInstaller 打包成可执行文件后由 Electron 拉起：
- 数据写入用户目录（Windows 为 %LOCALAPPDATA%\\BidAgent），避免安装目录只读
- 清空 REDIS_URL，改用进程内线程池，桌面环境无需额外部署 Redis
- 同时托管前端构建产物，Electron 直接加载 http://127.0.0.1:<port>/
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
from pathlib import Path


def _resource_root() -> Path:
    """PyInstaller 解包目录（_MEIPASS）或 backend 源码目录。"""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _frontend_dist() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return _resource_root() / "frontend" / "dist"
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _user_data_root() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "BidAgent"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BidAgent"
    return Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "BidAgent"


def _ensure_secret(path: Path) -> str:
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
    value = os.urandom(32).hex()
    path.write_text(value, encoding="utf-8")
    return value


def _sync_knowledge_base(resource_root: Path, target: Path) -> None:
    """首次运行时把内置知识库示例复制到用户目录，已有内容不覆盖。"""
    source = resource_root / "knowledge_base"
    if not source.is_dir():
        return
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        return
    shutil.copytree(source, target, dirs_exist_ok=True)


def _free_port(preferred: int = 8080) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 20)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def configure_environment() -> int:
    resource_root = _resource_root()
    data_root = _user_data_root()
    data_dir = data_root / "data"
    (data_dir / "tmp").mkdir(parents=True, exist_ok=True)
    (data_dir / "generated").mkdir(parents=True, exist_ok=True)
    _sync_knowledge_base(resource_root, data_dir / "kb")

    os.environ["BID_SYSTEM_ENV"] = "development"
    os.environ.setdefault("BID_SYSTEM_DEBUG", "false")
    os.environ["BID_SYSTEM_SECRET_KEY"] = _ensure_secret(data_root / "secret.key")
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["TEMP_DIR"] = str(data_dir / "tmp")
    os.environ["GENERATED_DIR"] = str(data_dir / "generated")
    os.environ["DATABASE_URL"] = f"sqlite:///{(data_dir / 'bid_agent.db').as_posix()}"
    os.environ["KNOWLEDGE_BASE_PATH"] = str(data_dir / "kb")
    os.environ["CHROMA_PERSIST_DIR"] = str(data_dir / "chroma_db")
    os.environ["REDIS_URL"] = ""
    os.environ["BIAOSHU_SKILL_PATH"] = ""
    os.environ["FRONTEND_DIST"] = str(_frontend_dist())
    return _free_port()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    port = configure_environment()
    import uvicorn

    from app.main import app

    print(f"BID_AGENT_PORT={port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
