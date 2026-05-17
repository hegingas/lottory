"""彩票 Web 展示启动入口

用法（在仓库根目录）:
    python src/scripts/lottery_web.py
    # 浏览器打开 http://localhost:5000
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 src/ 在 sys.path 中
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from lottery.web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
