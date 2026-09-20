"""开发启动入口：python run.py

自带虚拟环境引导：当检测到当前解释器不是项目 .venv 时，自动切换到
.venv 的解释器重新启动。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# backend/run.py -> parents[0]=backend, [1]=项目根
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent


def _venv_python() -> Path | None:
    """返回项目 .venv 的解释器路径（不存在则 None）。"""
    if os.name == "nt":
        candidate = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = PROJECT_ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else None


def _ensure_venv() -> None:
    """不在 .venv 中运行时，用 .venv 解释器重新启动本脚本。"""
    venv_py = _venv_python()
    if venv_py is None:
        return
    if Path(sys.executable).resolve() == venv_py.resolve():
        return

    print(f"[run.py] 切换到虚拟环境：{venv_py}")
    args = [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]]
    try:
        completed = subprocess.run(args, cwd=str(BACKEND_DIR))
    except KeyboardInterrupt:
        sys.exit(0)
    sys.exit(completed.returncode)


def _check_dependencies() -> None:
    """依赖缺失时给出明确的安装指引，而不是裸 ModuleNotFoundError。"""
    try:
        import sqlalchemy  # noqa: F401
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"[run.py] 缺少依赖：{exc.name}")
        print("请先安装依赖：")
        print(f'  "{sys.executable}" -m pip install -r requirements.txt')
        print("  （web 通道还需：python -m playwright install chromium）")
        sys.exit(1)


if __name__ == "__main__":
    _ensure_venv()
    _check_dependencies()

    import uvicorn

    from app.config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
