"""WIP loop elements: clouds/flocks/shadows must exist and move. No noise."""

from PIL import Image

from scripts.loop_wip_elements import overlay_flocks, overlay_ground, overlay_clouds


def _alpha_sum(im: Image.Image) -> int:
    return sum(im.getchannel("A").getdata())


def test_flocks_and_ground_are_not_empty():
    a = overlay_flocks(1.0)
    b = overlay_ground(1.0)
    assert _alpha_sum(a) > 0
    assert _alpha_sum(b) > 0


def test_elements_travel_over_time():
    a0 = overlay_flocks(0.0).tobytes()
    a2 = overlay_flocks(2.0).tobytes()
    g0 = overlay_ground(0.0).tobytes()
    g2 = overlay_ground(2.0).tobytes()
    c0 = overlay_clouds(0.0).tobytes()
    c2 = overlay_clouds(2.0).tobytes()
    assert a0 != a2
    assert g0 != g2
    assert c0 != c2
