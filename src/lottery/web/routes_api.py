"""Flask Blueprint — JSON API 路由。"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ._helpers import (
    LOTTERY_META,
    _aggregate_backtest_api,
    _build_trend_table,
    _load_csv,
    _parse_dlt_ssq_numbers,
    _parse_kl8_numbers,
    _parse_pl5_numbers,
    _parse_qxc_numbers,
    build_trend_data,
    parse_prediction_md,
)

api = Blueprint("api", __name__)


@api.route("/api/<lt>/latest")
def api_latest(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    meta = LOTTERY_META[lt]
    df = _load_csv(lt)
    if df.empty:
        return jsonify({"error": "无数据"}), 404
    row = df.iloc[-1]
    return jsonify({
        "lottery_type": lt,
        "name": meta["name"],
        "period": int(row["period_id"]),
        "main_nums": [int(row[c]) for c in meta["main_cols"]],
        "sub_nums": [int(row[c]) for c in meta["sub_cols"]] if meta["sub_cols"] else [],
        "total_periods": len(df),
    })


@api.route("/api/<lt>/history")
def api_history(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    meta = LOTTERY_META[lt]
    df = _load_csv(lt)
    if df.empty:
        return jsonify({"data": [], "total": 0})

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    search = request.args.get("search", "", type=str)

    # 按 period_id 降序
    sorted_df = df.sort_values("period_id", ascending=False)
    if search:
        sorted_df = sorted_df[sorted_df["period_id"].astype(str).str.contains(search)]

    total = len(sorted_df)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = sorted_df.iloc[start:end]

    data = []
    for _, row in page_df.iterrows():
        data.append({
            "period": int(row["period_id"]),
            "main_nums": [int(row[c]) for c in meta["main_cols"]],
            "sub_nums": [int(row[c]) for c in meta["sub_cols"]] if meta["sub_cols"] else [],
        })

    return jsonify({"data": data, "total": total, "page": page, "per_page": per_page})


@api.route("/api/<lt>/trends")
def api_trends(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    window = request.args.get("window", 100, type=int)
    window = min(window, 500)
    data = build_trend_data(lt, window)
    return jsonify(data)


@api.route("/api/<lt>/trend-table")
def api_trend_table(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    window = request.args.get("window", 100, type=int)
    window = min(window, 500)
    data = _build_trend_table(lt, window)
    return jsonify(data)


@api.route("/api/<lt>/prediction")
def api_prediction(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    data = parse_prediction_md(lt)
    return jsonify(data)


@api.route("/api/<lt>/prediction-accuracy")
def api_prediction_accuracy(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    try:
        from ..db import compute_accuracy, get_predictions
    except Exception:
        return jsonify({"error": "数据库模块暂不可用"}), 500

    period_str = request.args.get("period", "", type=str)
    if period_str:
        try:
            period_id = int(period_str)
        except (ValueError, TypeError):
            return jsonify({"error": "期号格式错误"}), 400
    else:
        preds = get_predictions(lt)
        if not preds:
            return jsonify({"error": "暂无该彩种的预测记录"}), 404
        period_id = max(p["predicted_period_id"] for p in preds)

    result = compute_accuracy(lt, period_id)
    return jsonify(result)


@api.route("/api/<lt>/backtest-summary")
def api_backtest_summary(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    try:
        from ..db import get_backtest_results
    except Exception:
        return jsonify({"error": "数据库模块暂不可用"}), 500
    rows = get_backtest_results(lt)
    if not rows:
        return jsonify({"error": "暂无回测数据，请先运行 backtest 命令"}), 404
    # 聚合
    regulars = [r for r in rows if r["ticket_type"] == "regular"]
    bests = [r for r in rows if r["ticket_type"] == "best"]
    total_periods = len(set(r["predicted_period_id"] for r in rows))
    summary = {
        "lottery_type": lt,
        "total_periods": total_periods,
        "total_records": len(rows),
        "regular": _aggregate_backtest_api(lt, regulars),
        "best": _aggregate_backtest_api(lt, bests),
    }
    return jsonify(summary)


@api.route("/api/<lt>/backtest-results")
def api_backtest_results_detail(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    try:
        from ..db import get_backtest_results
    except Exception:
        return jsonify({"error": "数据库模块暂不可用"}), 500
    rows = get_backtest_results(lt)
    if not rows:
        return jsonify({"error": "暂无回测数据"}), 404
    limit = request.args.get("limit", 30, type=int)
    # 每期聚合：取 best ticket 的命中 + 5注均值
    by_period: dict[int, dict] = {}
    for r in rows:
        pid = r["predicted_period_id"]
        if pid not in by_period:
            by_period[pid] = {"period": pid, "regular": [], "best": None}
        if r["ticket_type"] == "regular":
            by_period[pid]["regular"].append(r)
        elif r["ticket_type"] == "best":
            by_period[pid]["best"] = r
    result = []
    for pid in sorted(by_period.keys(), reverse=True)[:limit]:
        pd_data = by_period[pid]
        item: dict = {"period": pid}
        regs = pd_data["regular"]
        if lt in ("dlt",):
            item["avg_front"] = round(sum(r.get("front_matches", 0) for r in regs) / len(regs), 2) if regs else 0
            item["avg_back"] = round(sum(r.get("back_matches", 0) for r in regs) / len(regs), 2) if regs else 0
            if pd_data["best"]:
                item["best_front"] = pd_data["best"].get("front_matches", 0)
                item["best_back"] = pd_data["best"].get("back_matches", 0)
                item["best_prize"] = pd_data["best"].get("prize_level", "")
        elif lt == "ssq":
            item["avg_red"] = round(sum(r.get("red_matches", 0) for r in regs) / len(regs), 2) if regs else 0
            item["avg_blue"] = round(sum(r.get("blue_match", 0) for r in regs) / len(regs), 2) if regs else 0
            if pd_data["best"]:
                item["best_red"] = pd_data["best"].get("red_matches", 0)
                item["best_blue"] = pd_data["best"].get("blue_match", 0)
                item["best_prize"] = pd_data["best"].get("prize_level", "")
        elif lt == "kl8":
            item["avg_overlap"] = round(sum(r.get("overlap_count", 0) for r in regs) / len(regs), 2) if regs else 0
            if pd_data["best"]:
                item["best_overlap"] = pd_data["best"].get("overlap_count", 0)
        elif lt == "pl5":
            item["avg_pos"] = round(sum(r.get("position_matches", 0) for r in regs) / len(regs), 2) if regs else 0
            if pd_data["best"]:
                item["best_pos"] = pd_data["best"].get("position_matches", 0)
        elif lt == "qxc":
            item["avg_front"] = round(sum(r.get("front_matches", 0) for r in regs) / len(regs), 2) if regs else 0
            item["avg_special"] = round(sum(r.get("special_match", 0) for r in regs) / len(regs), 2) if regs else 0
            if pd_data["best"]:
                item["best_front"] = pd_data["best"].get("front_matches", 0)
                item["best_special"] = pd_data["best"].get("special_match", 0)
        result.append(item)
    return jsonify({"lottery_type": lt, "results": result})


@api.route("/api/<lt>/check-wins", methods=["POST"])
def api_check_wins(lt: str):
    if lt not in LOTTERY_META:
        return jsonify({"error": "彩种不存在"}), 404
    meta = LOTTERY_META[lt]
    df = _load_csv(lt)
    if df.empty:
        return jsonify({"error": "无数据"}), 404

    body = request.get_json(silent=True) or {}
    raw = body.get("numbers", "")
    if not raw:
        return jsonify({"error": "未提供号码"}), 400

    # ── 解析号码 ──
    parsed = None
    if lt in ("dlt", "ssq"):
        parsed = _parse_dlt_ssq_numbers(raw, lt)
        if parsed is None:
            return jsonify({"error": "无法解析号码，期望格式：前区 xx xx xx xx xx；后区 xx xx"}), 400
    elif lt == "kl8":
        parsed = _parse_kl8_numbers(raw)
        if parsed is None:
            return jsonify({"error": "无法解析号码"}), 400
    elif lt == "pl5":
        parsed = _parse_pl5_numbers(raw)
        if parsed is None:
            return jsonify({"error": "无法解析号码，期望 5 位数字"}), 400
    elif lt == "qxc":
        parsed = _parse_qxc_numbers(raw)
        if parsed is None:
            return jsonify({"error": "无法解析号码，期望前 6 + 后 1 共 7 个数字"}), 400

    # ── 逐期匹配 ──
    matches = []
    if lt in ("dlt", "ssq"):
        main_set = set(parsed["main"])
        sub_set = set(parsed["sub"])
        threshold_main = 3
        threshold_sub = 1

        for _, row in df.iterrows():
            row_main = {int(row[c]) for c in meta["main_cols"]}
            row_sub = {int(row[c]) for c in meta["sub_cols"]} if meta["sub_cols"] else set()
            main_hit = len(main_set & row_main)
            sub_hit = len(sub_set & row_sub) if row_sub else 0
            # 阈值过滤
            if main_hit >= threshold_main or (main_hit >= 2 and sub_hit >= threshold_sub):
                matches.append({
                    "period": int(row["period_id"]),
                    "main_hit": main_hit,
                    "sub_hit": sub_hit,
                    "main_hit_nums": sorted(main_set & row_main),
                    "sub_hit_nums": sorted(sub_set & row_sub) if row_sub else [],
                    "main_drawn": sorted(row_main),
                    "sub_drawn": sorted(row_sub) if row_sub else [],
                })

    elif lt == "kl8":
        cand_set = set(parsed["candidates"])
        threshold = 4
        for _, row in df.iterrows():
            drawn = {int(row[c]) for c in meta["main_cols"]}
            hit = len(cand_set & drawn)
            if hit >= threshold:
                matches.append({
                    "period": int(row["period_id"]),
                    "hit_count": hit,
                    "hit_nums": sorted(cand_set & drawn),
                    "drawn_nums": sorted(drawn),
                })

    elif lt == "pl5":
        digits = parsed["digits"]
        threshold = 3
        for _, row in df.iterrows():
            drawn = [int(row[c]) for c in meta["main_cols"]]
            pos_hits = [digits[i] == drawn[i] for i in range(5)]
            hit_count = sum(pos_hits)
            if hit_count >= threshold:
                matches.append({
                    "period": int(row["period_id"]),
                    "pos_hits": pos_hits,
                    "hit_count": hit_count,
                    "drawn_digits": drawn,
                })

    elif lt == "qxc":
        front = parsed["front"]
        special = parsed["special"]
        threshold = 3
        for _, row in df.iterrows():
            drawn_front = [int(row[c]) for c in meta["main_cols"]]
            drawn_special = int(row[meta["sub_cols"][0]]) if meta["sub_cols"] else None
            front_hits = [front[i] == drawn_front[i] for i in range(6)]
            special_hit = (special == drawn_special) if drawn_special is not None else False
            total_hit = sum(front_hits) + (1 if special_hit else 0)
            if total_hit >= threshold:
                matches.append({
                    "period": int(row["period_id"]),
                    "front_pos_hits": front_hits,
                    "special_hit": special_hit,
                    "hit_count": total_hit,
                    "drawn_front": drawn_front,
                    "drawn_special": drawn_special,
                })

    # ── 排序 & 截断 ──
    if lt in ("dlt", "ssq"):
        matches.sort(key=lambda m: (m["main_hit"], m["sub_hit"]), reverse=True)
    elif lt in ("pl5", "qxc"):
        matches.sort(key=lambda m: m["hit_count"], reverse=True)
    else:
        matches.sort(key=lambda m: m["hit_count"], reverse=True)

    best = matches[0] if matches else None
    matches = matches[:50]

    result = {
        "lottery_type": lt,
        "input": parsed,
        "total_checked": len(df),
        "match_count": len(matches),
        "matches": matches,
        "best_match": best,
    }
    return jsonify(result)


@api.route("/api/meta")
def api_meta():
    return jsonify(LOTTERY_META)


@api.route("/api/overview")
def api_overview():
    overview = {}
    for lt, meta in LOTTERY_META.items():
        df = _load_csv(lt)
        if df.empty:
            overview[lt] = None
            continue
        row = df.iloc[-1]
        overview[lt] = {
            "name": meta["name"],
            "latest_period": int(row["period_id"]),
            "latest_main": [int(row[c]) for c in meta["main_cols"]],
            "latest_sub": [int(row[c]) for c in meta["sub_cols"]] if meta["sub_cols"] else [],
            "total_periods": len(df),
        }
    return jsonify(overview)
