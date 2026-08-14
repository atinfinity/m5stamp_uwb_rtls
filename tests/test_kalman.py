import math
import random

from server.positioning.kalman import CvKalman2D


def test_straight_line_tracking():
    rng = random.Random(2)
    kf = CvKalman2D(sigma_a=1.0)
    dt = 0.5
    errs = []
    raw_errs = []
    for i in range(60):
        tx, ty = 1.0 * i * dt, 0.5 * i * dt  # 真値: 等速直線 (1.0, 0.5) m/s
        zx, zy = tx + rng.gauss(0, 0.1), ty + rng.gauss(0, 0.1)
        if not kf.initialized:
            kf.init(zx, zy, 0.15)
        else:
            kf.predict(dt)
            kf.update(zx, zy, 0.15)
        x, y, vx, vy = kf.state()
        if i > 20:  # 収束後のみ評価
            errs.append(math.hypot(x - tx, y - ty))
            raw_errs.append(math.hypot(zx - tx, zy - ty))
    # フィルタ後は生観測より改善し、絶対値でも 15 cm 未満
    # (sigma_a=1.0 は歩行の機動を許容する設定のため平滑化は控えめ)
    assert sum(errs) / len(errs) < sum(raw_errs) / len(raw_errs)
    assert sum(errs) / len(errs) < 0.15
    _, _, vx, vy = kf.state()
    assert abs(vx - 1.0) < 0.2 and abs(vy - 0.5) < 0.2


def test_predict_only_coasting():
    kf = CvKalman2D(sigma_a=1.0)
    kf.init(0.0, 0.0, 0.15)
    for _ in range(10):
        kf.predict(0.5)
        kf.update(kf.state()[0] + 0.5, kf.state()[1], 0.15)  # x 方向 1 m/s 相当
    x0, _, _, _ = kf.state()
    kf.predict(0.5)  # 欠測エポック: 予測のみ
    x1, _, vx, _ = kf.state()
    assert x1 > x0  # 速度で外挿されている
    assert vx > 0.5
