import pytest
from PIL import Image
from lib.qa.diversity_gate import audit_frame_luminance, LuminanceContrastGate


def test_audit_frame_luminance_fails_on_under_illuminated_frames():
    # 100x100 image: 95% black, 5% dim orange (like Moku's faint cone)
    im = Image.new("RGB", (100, 100), (2, 2, 2))
    # Draw tiny faint cone
    for x in range(45, 55):
        for y in range(45, 55):
            im.putpixel((x, y), (35, 20, 5))
            
    passed, code, msg, details = audit_frame_luminance(im, min_mean_y=22.0, max_dark_ratio=0.85)
    assert not passed
    assert code == "ERR_QA_UNDER_ILLUMINATED_SCENE"
    assert "luminance" in msg.lower() or "darkness" in msg.lower()


def test_audit_frame_luminance_passes_on_well_lit_cinematic_frame():
    # 100x100 image: good cinematic balance
    im = Image.new("RGB", (100, 100), (30, 30, 35))
    for x in range(20, 80):
        for y in range(20, 80):
            im.putpixel((x, y), (120, 100, 70))
            
    passed, code, msg, details = audit_frame_luminance(im, min_mean_y=22.0, max_dark_ratio=0.85)
    assert passed
    assert code == "OK_LUMINANCE_COMPLIANT"
