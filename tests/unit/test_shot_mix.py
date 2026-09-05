"""Live director mix: majority settled, no catalog bake."""

from src.agents.shot_mix import DESIGNED, SETTLED, assign_roles, designed_count


def test_five_scenes_three_or_four_settled():
    roles = assign_roles(5)
    assert len(roles) == 5
    assert roles.count(SETTLED) in (3, 4)
    assert roles.count(DESIGNED) in (1, 2)
    assert roles.count(SETTLED) > roles.count(DESIGNED)


def test_four_scenes_one_designed():
    roles = assign_roles(4)
    assert roles.count(SETTLED) == 3
    assert roles.count(DESIGNED) == 1


def test_single_scene_is_settled_no_negotiation():
    assert assign_roles(1) == [SETTLED]


def test_designed_never_outnumbers_settled():
    for n in range(0, 21):
        roles = assign_roles(n)
        assert len(roles) == n
        assert roles.count(DESIGNED) == designed_count(n)
        assert roles.count(SETTLED) >= roles.count(DESIGNED)


def test_catalog_shots_reuse_settled_background():
    from src.pipeline import _catalog_shots_from_manifest

    class Engine:
        def __init__(self) -> None:
            self.n = 0

        def resolve_loop_video(self, category, allow_fallback=True, orientation="vertical", seed=None):
            self.n += 1
            return f"/tmp/loop_{self.n}.mp4"

    manifest = {"scenes": [{"duration_sec": 8, "category": "x"} for _ in range(4)]}
    paths, durs, _cat = _catalog_shots_from_manifest(manifest, Engine(), "vertical")
    assert durs == [8.0, 8.0, 8.0, 8.0]
    assert paths[0] == paths[1] == paths[2]
    assert paths[3] != paths[0]


def test_designed_filter_is_not_the_settled_grade():
    from src.agents.shot_mix import video_filter_for_role

    settled = video_filter_for_role(SETTLED, 1080, 1920, 30)
    designed = video_filter_for_role(DESIGNED, 1080, 1920, 30)
    assert "colorchannelmixer" not in settled
    assert "colorchannelmixer" in designed
    assert designed != settled
