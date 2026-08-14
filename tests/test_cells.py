from server.cells import CellManager


def test_basic_containment(config):
    cm = CellManager(config)
    assert cm.select(5.0, 5.0, None) == "A"
    assert cm.select(40.0, 5.0, None) == "B"
    assert cm.select(5.0, 40.0, None) == "C"
    assert cm.select(40.0, 40.0, None) == "D"


def test_hysteresis_holds_near_boundary(config):
    cm = CellManager(config)
    # セル A (0..25) の境界 25m 付近: margin 2m 以内なら A を維持
    assert cm.select(26.0, 10.0, "A") == "A"
    # margin を超えたら B へハンドオーバー
    assert cm.select(28.0, 10.0, "A") == "B"


def test_no_flapping_walk_across_boundary(config):
    cm = CellManager(config)
    cell = "A"
    changes = 0
    xs = [24.0, 24.8, 25.2, 24.9, 25.5, 26.1, 26.8, 27.5, 28.2, 29.0]
    for x in xs:
        new = cm.select(x, 10.0, cell)
        if new != cell:
            changes += 1
            cell = new
    assert changes == 1  # 境界を行き来しても切替は 1 回だけ
    assert cell == "B"


def test_anchors_of(config):
    cm = CellManager(config)
    assert cm.anchors_of("A") == [0x0010, 0x0011, 0x0013, 0x0014]


def test_acquisition_cell_is_defined(config):
    cm = CellManager(config)
    assert cm.acquisition_cell() in config.cells
