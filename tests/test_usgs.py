"""Shaking grid, exposure parsing and the fallback intensity formula. No network."""

import math

import pytest

from airlift.usgs import Exposure, ShakeGrid, estimate_mmi, fetch_event


def plane(lat, lon):
    return 0.5 * lat + 0.25 * lon


def covjson(x0, x1, nx, y0, y1, ny, fn=plane):
    """A CoverageJSON grid whose value is a plane, so bilinear interpolation must be exact."""
    values = []
    for iy in range(ny):
        lat = y0 + (y1 - y0) * iy / (ny - 1)
        for ix in range(nx):
            values.append(fn(lat, x0 + (x1 - x0) * ix / (nx - 1)))
    return {
        "domain": {"axes": {"x": {"start": x0, "stop": x1, "num": nx}, "y": {"start": y0, "stop": y1, "num": ny}}},
        "ranges": {"MMI": {"axisNames": ["y", "x"], "values": values}},
    }


def test_bilinear_is_exact_on_a_plane():
    g = ShakeGrid.from_covjson(covjson(10, 14, 9, 20, 23, 7))
    for lat, lon in [(20, 10), (23, 14), (21.37, 12.81), (22.999, 10.001)]:
        assert g.mmi_at(lat, lon) == pytest.approx(plane(lat, lon), abs=1e-9)


def test_grid_listed_north_to_south_is_flipped():
    g = ShakeGrid.from_covjson(covjson(10, 14, 9, 23, 20, 7))   # y runs downward
    assert g.y0 < g.y1
    assert g.mmi_at(21.37, 12.81) == pytest.approx(plane(21.37, 12.81), abs=1e-9)


def test_outside_the_grid_is_not_felt():
    g = ShakeGrid.from_covjson(covjson(10, 14, 9, 20, 23, 7))
    assert g.mmi_at(19.99, 12) == 1.0
    assert g.mmi_at(21, 14.01) == 1.0
    assert not g.covers(19.99, 12)
    assert g.covers(20, 10) and g.covers(23, 14)


def test_empty_cells_read_as_not_felt_and_are_skipped():
    cov = covjson(10, 14, 9, 20, 23, 7)
    cov["ranges"]["MMI"]["values"][0] = None
    g = ShakeGrid.from_covjson(cov)
    assert g.mmi_at(20.0, 10.0) == 1.0
    assert all(not math.isnan(m) for _, _, m in g.cells())
    assert len(list(g.cells())) == 9 * 7 - 1


def test_grid_across_the_180th_meridian():
    # USGS writes such grids with longitudes beyond -180. An airport at +179.5 is inside.
    def shaking(lat, lon):
        return 6 + 0.2 * (lon + 182) + 0.1 * (lat + 20)

    g = ShakeGrid.from_covjson(covjson(-182, -176, 13, -20, -15, 11, fn=shaking))
    assert g.covers(-17, 179.5)
    assert g.mmi_at(-17, 179.5) == pytest.approx(shaking(-17, -180.5), abs=1e-9)
    assert g.mmi_at(-17, -179.0) == pytest.approx(shaking(-17, -179.0), abs=1e-9)
    assert not g.covers(-17, 170)


def test_degenerate_grid_is_rejected():
    with pytest.raises(ValueError):
        ShakeGrid(0, 1, 1, 0, 1, 5, [5.0] * 5)
    with pytest.raises(ValueError):
        ShakeGrid(0, 1, 3, 0, 1, 3, [5.0] * 8)


def grid_xml(nlon, nlat, lon0=10.0, lat0=20.0, step=0.5):
    """A legacy grid.xml, written north to south like USGS does, with MMI in the 5th column."""
    rows = []
    for iy in reversed(range(nlat)):
        for ix in range(nlon):
            lat, lon = lat0 + iy * step, lon0 + ix * step
            rows.append(f"{lon} {lat} 1.0 2.0 {plane(lat, lon)} 9.9")
    return (
        '<shakemap_grid xmlns="http://earthquake.usgs.gov/eqcenter/shakemap">'
        f'<grid_specification lon_min="{lon0}" lat_min="{lat0}" lon_max="{lon0 + (nlon - 1) * step}" '
        f'lat_max="{lat0 + (nlat - 1) * step}" nlon="{nlon}" nlat="{nlat}"/>'
        '<grid_field index="1" name="LON"/><grid_field index="2" name="LAT"/><grid_field index="3" name="PGA"/>'
        '<grid_field index="4" name="PGV"/><grid_field index="5" name="MMI"/><grid_field index="6" name="PSA03"/>'
        "<grid_data>\n" + "\n".join(rows) + "\n</grid_data></shakemap_grid>"
    ).encode()


def test_legacy_grid_xml_full_resolution():
    g = ShakeGrid.from_grid_xml(grid_xml(9, 7))
    assert (g.nx, g.ny) == (9, 7)
    assert g.mmi_at(21.3, 12.2) == pytest.approx(plane(21.3, 12.2), abs=1e-9)


def test_legacy_grid_xml_downsampled_keeps_alignment():
    # 10 x 8 cells with max_n=5 forces a stride of 2; (n-1) is not divisible by the stride.
    g = ShakeGrid.from_grid_xml(grid_xml(10, 8), max_n=5)
    assert (g.nx, g.ny) == (5, 4)
    assert g.x1 == pytest.approx(10 + 8 * 0.5) and g.y1 == pytest.approx(20 + 6 * 0.5)
    assert g.mmi_at(21.3, 12.2) == pytest.approx(plane(21.3, 12.2), abs=1e-9)


# Allen, Wald and Worden (2012), hypocentral-distance form. Reference values are
# OpenQuake's test table for its independent implementation:
# openquake/hazardlib/tests/gsim/data/a12ipe/AWW_IPE_RHYPO_MEAN.csv
OPENQUAKE_TABLE = [
    (5.0, 1.0, 8.1928149), (5.0, 5.0, 6.8801720), (5.0, 10.0, 5.9736099), (5.0, 20.0, 5.0191197),
    (5.0, 50.0, 3.7394023), (5.0, 100.0, 2.8223814), (5.0, 300.0, 1.3680280),
    (6.0, 1.0, 8.2797327), (6.0, 5.0, 7.8627966), (6.0, 10.0, 7.2488079), (6.0, 20.0, 6.4046804),
    (6.0, 50.0, 5.1603881), (6.0, 100.0, 4.2486195), (6.0, 300.0, 2.7958320),
    (7.0, 1.0, 8.2924672), (7.0, 5.0, 8.2206291), (7.0, 10.0, 8.0343509), (7.0, 20.0, 7.5721877),
    (7.0, 50.0, 6.5368604), (7.0, 100.0, 5.6632662), (7.0, 300.0, 4.2223319),
]


@pytest.mark.parametrize("mag,rhypo,expected", OPENQUAKE_TABLE)
def test_fallback_formula_matches_openquake(mag, rhypo, expected):
    assert estimate_mmi(mag, depth_km=0.0, epicentral_km=rhypo) == pytest.approx(expected, abs=1e-6)


def test_fallback_formula_uses_hypocentral_distance():
    assert estimate_mmi(6.5, depth_km=30, epicentral_km=40) == pytest.approx(estimate_mmi(6.5, 0, 50), abs=1e-12)


def test_pager_json_exposure_and_us_region_codes():
    exp = Exposure.from_json({"population_exposure": {
        "mmi": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "aggregated_exposure": [0, 0, 0, 10, 20, 30, 400, 50, 6, 0],
        "country_exposures": [
            {"country_code": "WU", "exposure": [0, 0, 0, 10, 20, 30, 395, 50, 6, 0]},   # PAGER's code for the western US
            {"country_code": "CA", "exposure": [0, 0, 0, 0, 0, 0, 5, 0, 0, 0]},
        ]}})
    assert exp.at_least(7) == 456 and exp.at_least(8) == 56
    assert exp.main_country(valid={"US", "CA"}) == "US"


def test_pager_xml_bins_by_rounded_intensity():
    exp = Exposure.from_pager_xml(
        '<pager ccode="NP"><exposure dmin="6.5" dmax="7.5" exposure="100"/>'
        '<exposure dmin="7.5" dmax="8.5" exposure="40"/><city name="x"><exposure/></city></pager>')
    assert exp.by_mmi == {7: 100, 8: 40}
    assert exp.main_country() == "NP"


@pytest.mark.parametrize("bad", ["../..", "..", "a/b", "", "us7000 pn9s", "x" * 200, "/etc/passwd"])
def test_event_id_cannot_escape_the_cache(bad):
    with pytest.raises(ValueError):
        fetch_event(bad, refresh=True)
