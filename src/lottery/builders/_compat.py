"""兼容旧接口：dlt_explicit_from_patterns, ssq_explicit_from_patterns。"""

from __future__ import annotations

import numpy as np

from ..config import (
    DLT_BACK_MAX_ACTIVE_ZONES,
    DLT_BACK_MAX_PER_ZONE,
    DLT_BACK_ZONES_CAP,
    DLT_FRONT_MAX_ACTIVE_ZONES,
    DLT_FRONT_MAX_PER_ZONE,
    DLT_FRONT_ZONES_CAP,
    SSQ_BLUE_MAX_ACTIVE_ZONES,
    SSQ_BLUE_MAX_PER_ZONE,
    SSQ_BLUE_ZONES_CAP,
    SSQ_RED_MAX_ACTIVE_ZONES,
    SSQ_RED_MAX_PER_ZONE,
    SSQ_RED_ZONES_CAP,
)
from ..interval_markov import (
    expand_mask_until_pickable,
    markov_next_bitmap_blended,
    mask_to_allowed_balls,
    valid_mask_set,
)
from ..markdown_utils import _fmt2
from ..scoring import (
    _dlt_back_scores,
    _dlt_front_scores,
    _markov_blended_probabilities,
    _ssq_blue_scores,
    _ssq_red_scores,
)
from ..selection import (
    _dlt_collect_five_unique_tickets,
    _ssq_collect_five_unique_tickets,
)


def dlt_explicit_from_patterns(
    f_draws: list[list[int]],
    b_draws: list[list[int]],
    fq: np.ndarray,
    fcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
) -> tuple[str, str]:
    f_mk = _markov_blended_probabilities(f_draws, 35)
    b_mk = _markov_blended_probabilities(b_draws, 12)
    fs = _dlt_front_scores(f_draws, fq, fcur, f_mk)
    bs = _dlt_back_scores(b_draws, bq, bcur, b_mk)
    fa = [list(map(int, row)) for row in f_draws]
    ba = [list(map(int, row)) for row in b_draws]
    _, mf, _, _, _, _, _ = markov_next_bitmap_blended(fa, DLT_FRONT_ZONES_CAP, valid_set=valid_mask_set(7, DLT_FRONT_MAX_ACTIVE_ZONES))
    af = mask_to_allowed_balls(
        expand_mask_until_pickable(mf, DLT_FRONT_ZONES_CAP, DLT_FRONT_MAX_PER_ZONE, 5),
        DLT_FRONT_ZONES_CAP,
    )
    _, mb, _, _, _, _, _ = markov_next_bitmap_blended(ba, DLT_BACK_ZONES_CAP, valid_set=valid_mask_set(4, DLT_BACK_MAX_ACTIVE_ZONES))
    ab = mask_to_allowed_balls(
        expand_mask_until_pickable(mb, DLT_BACK_ZONES_CAP, DLT_BACK_MAX_PER_ZONE, 2),
        DLT_BACK_ZONES_CAP,
    )
    f0, b0 = _dlt_collect_five_unique_tickets(fs, bs, allowed_front=af, allowed_back=ab)[0]
    return ",".join(_fmt2(x) for x in f0), ",".join(_fmt2(x) for x in b0)


def ssq_explicit_from_patterns(
    r_draws: list[list[int]],
    blues: list[int],
    rq: np.ndarray,
    rcur: np.ndarray,
    bq: np.ndarray,
    bcur: np.ndarray,
) -> tuple[str, str]:
    r_mk = _markov_blended_probabilities(r_draws, 33)
    b_mk = _markov_blended_probabilities([[int(x)] for x in blues], 16)
    rs = _ssq_red_scores(r_draws, rq, rcur, r_mk)
    bs = _ssq_blue_scores(blues, bq, bcur, b_mk)
    ra = [list(map(int, row)) for row in r_draws]
    ba = [[int(b)] for b in blues]
    _, mr, _, _, _, _, _ = markov_next_bitmap_blended(ra, SSQ_RED_ZONES_CAP, valid_set=valid_mask_set(7, SSQ_RED_MAX_ACTIVE_ZONES))
    ar = mask_to_allowed_balls(
        expand_mask_until_pickable(mr, SSQ_RED_ZONES_CAP, SSQ_RED_MAX_PER_ZONE, 6),
        SSQ_RED_ZONES_CAP,
    )
    _, mbl, _, _, _, _, _ = markov_next_bitmap_blended(ba, SSQ_BLUE_ZONES_CAP, valid_set=valid_mask_set(4, SSQ_BLUE_MAX_ACTIVE_ZONES))
    abl = mask_to_allowed_balls(
        expand_mask_until_pickable(mbl, SSQ_BLUE_ZONES_CAP, SSQ_BLUE_MAX_PER_ZONE, 1),
        SSQ_BLUE_ZONES_CAP,
    )
    r0, b0 = _ssq_collect_five_unique_tickets(rs, bs, allowed_red=ar, allowed_blue=abl)[0]
    return ",".join(_fmt2(x) for x in r0), _fmt2(b0)
