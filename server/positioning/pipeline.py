"""タグごとの解算パイプライン (server-design.md §5)。

process(RangeSet) -> Position | None を同期実装する。MQTT には依存しない。
"""
from __future__ import annotations

from server.config import RtlsConfig
from server.models import Position, Range, RangeSet, TagTrackState
from server.positioning import geometry, outlier
from server.positioning.kalman import CvKalman2D


class TagPipeline:
    def __init__(self, tag: int, config: RtlsConfig, cell_manager=None) -> None:
        self._tag = tag
        self._cfg = config
        self._anchors = config.anchor_by_addr()
        self._tuning = config.tuning
        self._kf = CvKalman2D(config.tuning.sigma_a)
        self._cells = cell_manager
        self._cell: str | None = None
        self._last_seq: int | None = None
        self._last_t_ms: int | None = None       # 最後に処理したエポック
        self._last_success_ms: int | None = None  # 最後に解算成功したエポック

    @property
    def cell(self) -> str | None:
        return self._cell

    # ---- ① 検証 ----

    def _validate(self, rs: RangeSet) -> bool:
        if self._last_seq is not None and rs.seq <= self._last_seq:
            return False
        if rs.recv_ms - rs.t_ms > self._tuning.max_age_ms:
            return False
        return True

    # ---- ②③ 補正とゲーティング ----

    def _usable_ranges(
        self, rs: RangeSet, dt_s: float
    ) -> tuple[list[tuple[int, tuple[float, float], float]], list[int]]:
        """採用した (アンカー, 座標, 水平距離) と、棄却したアンカーを返す。"""
        out: list[tuple[int, tuple[float, float], float]] = []
        rejected: list[int] = []
        predicted = None
        if self._kf.initialized:
            px, py, _, _ = self._kf.state()
            predicted = (px, py)
        for r in rs.ranges:
            if not r.ok:
                continue
            a = self._anchors.get(r.anchor)
            if a is None:
                continue
            slant_m = (r.d_mm - a.bias_mm) / 1000.0
            dz = a.z - self._cfg.floor.tag_height_m
            h = geometry.horizontal_range_m(slant_m, dz)
            if h is None:
                rejected.append(r.anchor)
                continue
            if predicted is not None and not outlier.gate(
                (a.x, a.y), h, predicted, self._tuning.v_max_ms, dt_s,
                self._tuning.gate_margin_m,
            ):
                rejected.append(r.anchor)
                continue
            out.append((r.anchor, (a.x, a.y), h))
        return out, rejected

    # ---- ④⑤⑥ 解算と外れ値除去 ----

    def _solve(self, usable: list[tuple[int, tuple[float, float], float]]):
        """(解, 使用アンカー, 追加棄却アンカー) を返す。"""
        anchors = [u[1] for u in usable]
        ranges = [u[2] for u in usable]
        addrs = [u[0] for u in usable]
        sol = geometry.solve_2d(anchors, ranges)
        if sol is None:
            return None, addrs, []
        worst = max(range(len(sol.residuals)), key=lambda i: abs(sol.residuals[i]))
        if abs(sol.residuals[worst]) > self._tuning.residual_gate_m and len(usable) >= 4:
            reduced = [u for i, u in enumerate(usable) if i != worst]
            sol2 = geometry.solve_2d([u[1] for u in reduced], [u[2] for u in reduced])
            if sol2 is not None and sol2.rms_residual < sol.rms_residual:
                return sol2, [u[0] for u in reduced], [addrs[worst]]
        return sol, addrs, []

    # ---- 本体 ----

    def process(self, rs: RangeSet) -> Position | None:
        if not self._validate(rs):
            return None
        self._last_seq = rs.seq

        dt_s = 0.0
        if self._last_t_ms is not None:
            dt_s = max((rs.t_ms - self._last_t_ms) / 1000.0, 1e-3)

        # LOST 判定: 長時間空いたらフィルタを作り直す
        if (self._last_success_ms is not None
                and (rs.t_ms - self._last_success_ms) / 1000.0 > self._tuning.lost_sec):
            self._kf.reset()
            self._last_success_ms = None

        self._last_t_ms = rs.t_ms
        usable, rejected = self._usable_ranges(rs, dt_s)

        if len(usable) < 3:
            # 欠測エポック: 予測のみ (COASTING)。フィルタ未初期化なら何も出せない。
            if not self._kf.initialized:
                return None
            self._kf.predict(dt_s)
            x, y, vx, vy = self._kf.state()
            state = self._staleness_state(rs.t_ms, default=TagTrackState.COASTING)
            return self._position(rs.t_ms, x, y, vx, vy, 0, 0.0, state,
                                  rejected=tuple(rejected))

        sol, used_addrs, loo_rejected = self._solve(usable)
        rejected.extend(loo_rejected)
        if sol is None:
            if not self._kf.initialized:
                return None
            self._kf.predict(dt_s)
            x, y, vx, vy = self._kf.state()
            state = self._staleness_state(rs.t_ms, default=TagTrackState.COASTING)
            return self._position(rs.t_ms, x, y, vx, vy, 0, 0.0, state,
                                  rejected=tuple(rejected))

        sigma_m = max(self._tuning.sigma_m_floor, sol.rms_residual)
        if not self._kf.initialized:
            self._kf.init(sol.x, sol.y, sigma_m)
        else:
            self._kf.predict(dt_s)
            self._kf.update(sol.x, sol.y, sigma_m)
        self._last_success_ms = rs.t_ms

        x, y, vx, vy = self._kf.state()
        return self._position(rs.t_ms, x, y, vx, vy, len(used_addrs), sol.rms_residual,
                              TagTrackState.TRACKING, used=tuple(used_addrs),
                              rejected=tuple(rejected))

    def _staleness_state(self, t_ms: int, default: TagTrackState) -> TagTrackState:
        if self._last_success_ms is None:
            return default
        gap_s = (t_ms - self._last_success_ms) / 1000.0
        if gap_s > self._tuning.lost_sec:
            return TagTrackState.LOST
        if gap_s > self._tuning.stale_sec:
            return TagTrackState.STALE
        return default

    def _position(self, t_ms: int, x: float, y: float, vx: float, vy: float,
                  n_used: int, residual: float, state: TagTrackState,
                  used: tuple[int, ...] = (), rejected: tuple[int, ...] = ()) -> Position:
        if self._cells is not None:
            self._cell = self._cells.select(x, y, self._cell)
        return Position(tag=self._tag, t_ms=t_ms, x_m=x, y_m=y, vx_ms=vx, vy_ms=vy,
                        n_used=n_used, residual_m=residual,
                        cell=self._cell or "", state=state,
                        used=used, rejected=rejected)
