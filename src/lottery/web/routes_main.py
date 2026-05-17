"""Flask Blueprint — 浏览器端页面路由。"""

from __future__ import annotations

from flask import Blueprint, render_template

from ._helpers import LOTTERY_META, _load_csv

main = Blueprint("main", __name__)


@main.route("/")
def index():
    latest = {}
    for lt, meta in LOTTERY_META.items():
        df = _load_csv(lt)
        if df.empty:
            latest[lt] = None
            continue
        row = df.iloc[-1]
        period = int(row["period_id"])
        main_nums = [int(row[c]) for c in meta["main_cols"]]
        sub_nums = [int(row[c]) for c in meta["sub_cols"]] if meta["sub_cols"] else []
        latest[lt] = {
            "period": period,
            "main_nums": main_nums,
            "sub_nums": sub_nums,
            "total": len(df),
        }
    return render_template("index.html", latest=latest, meta=LOTTERY_META)


@main.route("/<lt>")
def lottery_detail(lt: str):
    if lt not in LOTTERY_META:
        return render_template("base.html", content="<p>彩种不存在</p>"), 404
    meta = LOTTERY_META[lt]
    df = _load_csv(lt)
    last_row = df.iloc[-1] if not df.empty else None
    last_period = int(last_row["period_id"]) if last_row is not None else None
    last_main = (
        [int(last_row[c]) for c in meta["main_cols"]] if last_row is not None else []
    )
    last_sub = (
        [int(last_row[c]) for c in meta["sub_cols"]] if last_row is not None and meta["sub_cols"] else []
    )
    total = len(df)

    # 历史表格（最近 50 期用于初始渲染，更多通过 API 翻页）
    history_data = []
    if not df.empty:
        for _, row in df.tail(50).iloc[::-1].iterrows():
            history_data.append({
                "period": int(row["period_id"]),
                "main_nums": [int(row[c]) for c in meta["main_cols"]],
                "sub_nums": [int(row[c]) for c in meta["sub_cols"]] if meta["sub_cols"] else [],
            })

    return render_template(
        "lottery.html",
        lt=lt,
        meta=meta,
        last_period=last_period,
        last_main=last_main,
        last_sub=last_sub,
        total=total,
        history=history_data,
    )
