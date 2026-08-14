"""等速直線運動 (CV) モデルの 2D カルマンフィルタ (server-design.md §5 ⑦)。

状態 x = [x, y, vx, vy]。プロセスノイズは加速度白色雑音 sigma_a から構成。
"""
from __future__ import annotations

import numpy as np

_H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])


class CvKalman2D:
    def __init__(self, sigma_a: float) -> None:
        self._sigma_a2 = sigma_a * sigma_a
        self._x: np.ndarray | None = None
        self._p: np.ndarray | None = None

    @property
    def initialized(self) -> bool:
        return self._x is not None

    def reset(self) -> None:
        self._x = None
        self._p = None

    def init(self, x_m: float, y_m: float, sigma_m: float) -> None:
        self._x = np.array([x_m, y_m, 0.0, 0.0])
        # 初期速度は未知: 大きめの分散を与える
        self._p = np.diag([sigma_m**2, sigma_m**2, 4.0, 4.0])

    def predict(self, dt_s: float) -> None:
        assert self._x is not None and self._p is not None
        dt = max(dt_s, 1e-3)
        f = np.array(
            [[1, 0, dt, 0],
             [0, 1, 0, dt],
             [0, 0, 1, 0],
             [0, 0, 0, 1]], dtype=float)
        d4, d3, d2 = dt**4 / 4.0, dt**3 / 2.0, dt**2
        qb = self._sigma_a2 * np.array([[d4, d3], [d3, d2]])
        q = np.zeros((4, 4))
        q[np.ix_([0, 2], [0, 2])] = qb
        q[np.ix_([1, 3], [1, 3])] = qb
        self._x = f @ self._x
        self._p = f @ self._p @ f.T + q

    def update(self, x_m: float, y_m: float, sigma_m: float) -> None:
        assert self._x is not None and self._p is not None
        z = np.array([x_m, y_m])
        r = np.eye(2) * sigma_m**2
        s = _H @ self._p @ _H.T + r
        k = self._p @ _H.T @ np.linalg.inv(s)
        self._x = self._x + k @ (z - _H @ self._x)
        self._p = (np.eye(4) - k @ _H) @ self._p

    def state(self) -> tuple[float, float, float, float]:
        assert self._x is not None
        return float(self._x[0]), float(self._x[1]), float(self._x[2]), float(self._x[3])
