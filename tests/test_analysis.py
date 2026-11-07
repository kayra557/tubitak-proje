import pytest

from backend import analysis


def test_ndvi():
    assert analysis.ndvi(0.5, 0.1) == pytest.approx(0.6667, abs=1e-3)
    assert analysis.ndvi(0, 0) is None


def test_vci_bounds_and_classes():
    assert analysis.vci(0.2, [0.2, 0.6]) == 0
    assert analysis.vci(0.6, [0.2, 0.6]) == 100
    assert analysis.vci(0.4, [0.2, 0.6]) == pytest.approx(50)
    assert analysis.classify_vci(10)["key"] == "siddetli"
    assert analysis.classify_vci(30)["key"] == "orta"
    assert analysis.classify_vci(40)["key"] == "hafif"
    assert analysis.classify_vci(80)["key"] == "saglikli"
    assert analysis.classify_vci(None)["key"] == "veri_yok"


def test_linear_trend_detects_decline():
    t = analysis.linear_trend([2017, 2018, 2019, 2020], [0.6, 0.55, 0.5, 0.45])
    assert t["slope"] == pytest.approx(-0.05)
    assert t["r2"] == pytest.approx(1.0)
    assert t["percent_per_year"] < 0


def test_point_in_polygon_and_grid():
    sq = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    assert analysis.point_in_polygon(0.5, 0.5, sq)
    assert not analysis.point_in_polygon(1.5, 0.5, sq)
    assert len(analysis.grid_cells(sq, step=0.5)) == 4


def test_phenology_spring_peak():
    curve = [0.15, 0.17, 0.25, 0.4, 0.55, 0.45, 0.25, 0.18, 0.15, 0.15, 0.15, 0.15]
    p = analysis.phenology(curve)
    assert p["peak_month"] == 5
    assert p["green_up_month"] in (3, 4)
