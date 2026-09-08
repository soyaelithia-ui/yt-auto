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
    from src.agents.shot_mix import DESIGNED, SETTLED, assign_roles
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
    roles = assign_roles(4)
    settled_paths = {paths[i] for i, r in enumerate(roles) if r == SETTLED}
    designed_paths = {paths[i] for i, r in enumerate(roles) if r == DESIGNED}
    assert len(settled_paths) == 1
    assert roles.count(SETTLED) >= roles.count(DESIGNED)
    if designed_paths:
        assert settled_paths.isdisjoint(designed_paths)


def test_designed_filter_is_not_the_settled_grade():
    from src.agents.shot_mix import video_filter_for_role

    settled = video_filter_for_role(SETTLED, 1080, 1920, 30)
    designed = video_filter_for_role(DESIGNED, 1080, 1920, 30)
    assert "colorchannelmixer" not in settled
    assert "eq=contrast=" in settled  # light polish on settled
    assert "colorchannelmixer" in designed
    assert designed != settled


def test_catalog_shots_horizontal_rotates_backgrounds():
    from src.pipeline import _catalog_shots_from_manifest

    class Engine:
        def __init__(self) -> None:
            self.calls = []

        def resolve_loop_video(self, category, allow_fallback=True, orientation="vertical", seed=None, channel=None):
            self.calls.append({"cat": category, "orient": orientation, "seed": seed, "channel": channel})
            return f"/tmp/loop_{orientation}_{seed}.mp4"

    manifest = {"scenes": [{"duration_sec": 10, "category": f"cat_{i}"} for i in range(4)]}
    engine = Engine()
    paths, durs, _cat = _catalog_shots_from_manifest(manifest, engine, "horizontal", channel="moku")
    assert durs == [10.0, 10.0, 10.0, 10.0]
    assert len(set(paths)) == 4
    assert paths[0] != paths[1] != paths[2] != paths[3]
    assert engine.calls[0]["channel"] == "moku"
    assert engine.calls[0]["seed"] == 0
    assert engine.calls[1]["seed"] == 1



def test_designed_roles_are_spread():
    """Designed beats should not be piled only at the tail."""
    roles = assign_roles(5)
    assert roles.count(DESIGNED) in (1, 2)
    # With spread placement, index 0 should usually stay settled for a calm open.
    assert roles[0] == SETTLED or roles.count(DESIGNED) == roles.count(SETTLED)
    if DESIGNED in roles:
        first_d = roles.index(DESIGNED)
        last_d = len(roles) - 1 - roles[::-1].index(DESIGNED)
        # Not exclusively a suffix block starting at n-designed.
        assert first_d < len(roles) - roles.count(DESIGNED) or roles.count(DESIGNED) == 1
