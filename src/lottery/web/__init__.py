"""Flask Web 应用包 — 彩票开奖数据与预测展示。

使用 Flask Blueprints 拆分路由：
- routes_main.py: 浏览器端页面路由
- routes_api.py:  JSON API 路由
- _helpers.py:     辅助函数与数据（LOTTERY_META、统计计算、解析等）
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parents[3] / "templates"),
        static_folder=str(Path(__file__).resolve().parents[3] / "static"),
    )

    from .routes_api import api as api_bp
    from .routes_main import main as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)

    return app
