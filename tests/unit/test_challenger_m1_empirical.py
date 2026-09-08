"""
tests/unit/test_challenger_m1_empirical.py - Empirical Challenge & Stress-Test Suite for Milestone 1.

Empirically challenges and stress-tests:
1. Seeded Rotation Diversity: over 50 queries with different seeds, verifies distribution across multiple loops.
2. Channel Confinement: over 50 queries per channel, verifies 0 cross-channel leaks (even under adversarial category requests).
3. Multi-scene Exclusion: simulates 10-scene longform video, verifies 0 repeated loops while candidates remain available.
4. Category Aliases: tests 24 semantic alias strings, verifies each resolves to a valid, non-empty physical video loop.
5. Synthetic Monochrome Purge: verifies synthetic monochrome loops are never returned in regular queries.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Set

import pytest

from src.config import BASE_DIR, DEFAULT_DB_PATH
from src.core.catalog import (
    CHANNEL_CATEGORIES,
    LoopCatalogRepository,
    LoopRecord,
    SYNTHETIC_MONOCHROME_LOOP_IDS,
)
from src.media.loop_engine import CATEGORY_ALIASES, LoopVideoEngine

_LOOPS_ROOT = (BASE_DIR / "assets" / "loops").resolve()


def _asset_rel_parts(path: Path) -> list[str]:
    """Path parts under assets/loops so /home/moku is not a false channel leak."""
    resolved = Path(path).resolve()
    try:
        return [p.lower() for p in resolved.relative_to(_LOOPS_ROOT).parts]
    except ValueError:
        return [p.lower() for p in resolved.parts if p.lower() != "moku"]


@pytest.fixture(scope="module")
def isolated_catalog(tmp_path_factory) -> LoopCatalogRepository:
    """Isolated auto-seeded catalog; skip when repo has no committed loop media."""
    from src.config import BASE_DIR
    media = list((BASE_DIR / "assets" / "loops").rglob("*.mp4")) + list((BASE_DIR / "assets" / "loops").rglob("*.webm"))
    if len(media) < 50:
        pytest.skip("assets/loops has no committed cinematic media in this checkout")
    temp_dir = tmp_path_factory.mktemp("challenger_catalog")
    db_path = str(temp_dir / "challenger_autoseed.db")
    repo = LoopCatalogRepository(db_path=db_path, auto_seed=True)
    if repo.count_loops() < 50:
        pytest.skip(f"auto_seed yielded {repo.count_loops()} loops (<50); need committed media")
    return repo


@pytest.fixture(scope="module")
def isolated_engine(isolated_catalog: LoopCatalogRepository) -> LoopVideoEngine:
    """Returns a LoopVideoEngine instance connected to the isolated catalog."""
    return LoopVideoEngine(catalog=isolated_catalog)


@pytest.fixture(scope="module")
def production_catalog() -> LoopCatalogRepository:
    """Returns a LoopCatalogRepository connected to DEFAULT_DB_PATH."""
    repo = LoopCatalogRepository(db_path=DEFAULT_DB_PATH, auto_seed=True)
    return repo


class TestSeededRotationDiversity:
    """Challenge Dimension 1: Deterministic Seeded Rotation & Diversity."""

    def test_catalog_seeded_rotation_50_queries_diversity(self, isolated_catalog: LoopCatalogRepository):
        """
        Verify that over 50 queries with different seeds on a clean catalog, selections
        are widely distributed across available candidates (>= 15 unique loops chosen).
        """
        seeds = [i * 37 + 101 for i in range(50)]
        chosen_ids: List[str] = []

        for s in seeds:
            loop = isolated_catalog.get_best_loop(
                category="horror",
                orientation="horizontal",
                seed=s,
            )
            assert loop is not None, f"Expected loop for seed {s}"
            assert isinstance(loop, LoopRecord)
            assert loop.duration_sec > 0
            assert Path(loop.file_path).is_file()
            chosen_ids.append(loop.loop_id)

        unique_loops = set(chosen_ids)
        assert len(unique_loops) >= 15, (
            f"Expected at least 15 unique loops across 50 seeded queries, got only {len(unique_loops)}: {unique_loops}"
        )

    def test_engine_seeded_rotation_50_queries_diversity(self, isolated_engine: LoopVideoEngine):
        """
        Verify that LoopVideoEngine.resolve_loop_video exhibits high diversity
        over 50 queries with varying seeds as usage counts rotate.
        """
        seeds = [i * 13 + 7 for i in range(50)]
        chosen_paths: List[Path] = []

        for s in seeds:
            path = isolated_engine.resolve_loop_video(
                category="drama",
                orientation="horizontal",
                seed=s,
            )
            assert path.is_file(), f"Resolved path does not exist: {path}"
            assert path.stat().st_size >= 25_000, f"Resolved path is too small (<25KB): {path}"
            chosen_paths.append(path)

        unique_paths = set(chosen_paths)
        assert len(unique_paths) >= 15, (
            f"Expected at least 15 unique video paths across 50 seeds, got only {len(unique_paths)}"
        )

    def test_seeded_rotation_bit_exact_determinism(self, isolated_catalog: LoopCatalogRepository):
        """Verify that the exact same seed returns the identical loop ID consistently."""
        for seed_val in (0, 42, 999, 123456, 888888):
            first = isolated_catalog.get_best_loop(category="scifi", orientation="horizontal", seed=seed_val)
            second = isolated_catalog.get_best_loop(category="scifi", orientation="horizontal", seed=seed_val)
            assert first is not None and second is not None
            assert first.loop_id == second.loop_id, (
                f"Non-deterministic selection for seed {seed_val}: {first.loop_id} != {second.loop_id}"
            )

    @pytest.mark.parametrize("boundary_seed", [0, -1, -999999, 2**31 - 1, 2**63 - 1])
    def test_seeded_rotation_boundary_seeds(self, isolated_catalog: LoopCatalogRepository, boundary_seed: int):
        """Verify engine and catalog safely handle boundary seeds without crashing."""
        loop = isolated_catalog.get_best_loop(category="scifi", orientation="horizontal", seed=boundary_seed)
        assert loop is not None
        assert Path(loop.file_path).is_file()


class TestChannelConfinement:
    """Challenge Dimension 2: Channel Confinement & Isolation."""

    def test_moku_confinement_50_queries(self, isolated_catalog: LoopCatalogRepository):
        """
        Over 50 queries with channel='moku', verify that exactly 0 loops belonging to
        or tagged with Aelithia are returned.
        """
        categories = ["horror", "dark_forest", "cosmic_horror", "dark_ambient"]
        for i in range(50):
            cat = categories[i % len(categories)]
            orient = "horizontal" if i % 2 == 0 else "vertical"
            loop = isolated_catalog.get_best_loop(
                category=cat,
                orientation=orient,
                seed=i + 500,
                channel="moku",
            )
            assert loop is not None, f"Expected valid loop for moku query {i} (cat={cat}, orient={orient})"
            # Channel assertions
            assert loop.channel != "aelithia", f"Leak! Moku returned Aelithia loop: {loop.loop_id}"
            assert "aelithia" not in loop.theme_tags, f"Leak! Moku loop has aelithia in theme_tags: {loop.loop_id}"
            assert "aelithia" not in Path(loop.file_path).stem.lower(), f"Leak! File stem has aelithia: {loop.file_path}"
            assert "aelithia" not in loop.loop_id.lower(), f"Leak! Loop ID has aelithia: {loop.loop_id}"

    def test_aelithia_confinement_50_queries(self, isolated_catalog: LoopCatalogRepository):
        """
        Over 50 queries with channel='aelithia', verify that exactly 0 loops belonging to
        or tagged with Moku are returned.
        """
        categories = ["drama", "cozy_ambient", "nostalgia", "cozy_hearth"]
        for i in range(50):
            cat = categories[i % len(categories)]
            orient = "horizontal" if i % 2 == 0 else "vertical"
            loop = isolated_catalog.get_best_loop(
                category=cat,
                orientation=orient,
                seed=i + 1000,
                channel="aelithia",
            )
            assert loop is not None, f"Expected valid loop for aelithia query {i} (cat={cat}, orient={orient})"
            # Channel assertions
            assert loop.channel != "moku", f"Leak! Aelithia returned Moku loop: {loop.loop_id}"
            assert "moku" not in loop.theme_tags, f"Leak! Aelithia loop has moku in theme_tags: {loop.loop_id}"
            assert "moku" not in Path(loop.file_path).stem.lower(), f"Leak! File stem has moku: {loop.file_path}"
            assert "moku" not in loop.loop_id.lower(), f"Leak! Loop ID has moku: {loop.loop_id}"

    @pytest.mark.parametrize(
        "adversarial_cat",
        ["drama", "cozy_ambient", "reddit_aita", "cozy_hearth", "relationships"],
    )
    def test_adversarial_cross_category_moku_never_leaks_aelithia(
        self, isolated_catalog: LoopCatalogRepository, adversarial_cat: str
    ):
        """
        Adversarially request Aelithia-specific categories under channel='moku'.
        Verify that channel isolation holds and 0 Aelithia loops are returned.
        """
        for orient in ("horizontal", "vertical"):
            loop = isolated_catalog.get_best_loop(
                category=adversarial_cat,
                orientation=orient,
                channel="moku",
            )
            assert loop is not None, f"Expected fallback loop for moku on adversarial category {adversarial_cat}"
            assert loop.channel != "aelithia", (
                f"CRITICAL LEAK: Channel 'moku' requesting category '{adversarial_cat}' returned Aelithia loop: {loop.loop_id}"
            )
            assert "aelithia" not in loop.theme_tags

    @pytest.mark.parametrize(
        "adversarial_cat",
        ["horror", "dark_forest", "cosmic_horror", "tactical_chamber", "bunker"],
    )
    def test_adversarial_cross_category_aelithia_never_leaks_moku(
        self, isolated_catalog: LoopCatalogRepository, adversarial_cat: str
    ):
        """
        Adversarially request Moku-specific categories under channel='aelithia'.
        Verify that channel isolation holds and 0 Moku loops are returned.
        """
        for orient in ("horizontal", "vertical"):
            loop = isolated_catalog.get_best_loop(
                category=adversarial_cat,
                orientation=orient,
                channel="aelithia",
            )
            assert loop is not None, f"Expected fallback loop for aelithia on adversarial category {adversarial_cat}"
            assert loop.channel != "moku", (
                f"CRITICAL LEAK: Channel 'aelithia' requesting category '{adversarial_cat}' returned Moku loop: {loop.loop_id}"
            )
            assert "moku" not in loop.theme_tags

    def test_engine_channel_confinement_50_queries(self, isolated_engine: LoopVideoEngine):
        """
        Verify that LoopVideoEngine.resolve_loop_video strictly respects channel isolation
        across 50 queries.
        """
        for i in range(25):
            path_moku = isolated_engine.resolve_loop_video(
                category="horror",
                orientation="horizontal",
                channel="moku",
                seed=i + 200,
            )
            assert "aelithia" not in path_moku.stem.lower()
            assert "aelithia" not in _asset_rel_parts(path_moku)

            path_aelithia = isolated_engine.resolve_loop_video(
                category="drama",
                orientation="horizontal",
                channel="aelithia",
                seed=i + 300,
            )
            assert "moku" not in path_aelithia.stem.lower()
            assert "moku" not in _asset_rel_parts(path_aelithia)


class TestMultiSceneExclusion:
    """Challenge Dimension 3: Multi-scene Exclusion & Longform Pacing."""

    def test_10_scene_simulation_moku_horizontal(self, isolated_catalog: LoopCatalogRepository):
        """
        Simulate a 10-scene longform video for Moku.
        Iteratively accumulate chosen loop IDs into exclude_loop_ids.
        Verify that no loop is repeated across the 10 scenes.
        """
        chosen: List[str] = []
        for scene_idx in range(10):
            loop = isolated_catalog.get_best_loop(
                category="horror",
                orientation="horizontal",
                seed=scene_idx * 17 + 5,
                exclude_loop_ids=chosen,
                channel="moku",
            )
            assert loop is not None, f"Scene {scene_idx} returned None while candidates were available"
            assert loop.loop_id not in chosen, f"Scene {scene_idx} repeated loop {loop.loop_id}"
            chosen.append(loop.loop_id)

        assert len(chosen) == 10
        assert len(set(chosen)) == 10, f"Duplicated loops detected in 10-scene sequence: {chosen}"

    def test_10_scene_simulation_aelithia_horizontal(self, isolated_catalog: LoopCatalogRepository):
        """
        Simulate a 10-scene longform video for Aelithia.
        Verify that 10 distinct loops are chosen with zero repetition.
        """
        chosen: List[str] = []
        for scene_idx in range(10):
            loop = isolated_catalog.get_best_loop(
                category="drama",
                orientation="horizontal",
                seed=scene_idx * 19 + 7,
                exclude_loop_ids=chosen,
                channel="aelithia",
            )
            assert loop is not None, f"Scene {scene_idx} returned None"
            assert loop.loop_id not in chosen, f"Scene {scene_idx} repeated loop {loop.loop_id}"
            chosen.append(loop.loop_id)

        assert len(chosen) == 10
        assert len(set(chosen)) == 10

    def test_10_scene_simulation_scifi_horizontal(self, isolated_catalog: LoopCatalogRepository):
        """
        Simulate a 10-scene longform video for SciFi.
        Verify that 10 distinct loops are chosen with zero repetition.
        """
        chosen: List[str] = []
        for scene_idx in range(10):
            loop = isolated_catalog.get_best_loop(
                category="scifi",
                orientation="horizontal",
                seed=scene_idx * 23 + 11,
                exclude_loop_ids=chosen,
                channel="scifi",
            )
            assert loop is not None, f"Scene {scene_idx} returned None"
            assert loop.loop_id not in chosen, f"Scene {scene_idx} repeated loop {loop.loop_id}"
            chosen.append(loop.loop_id)

        assert len(chosen) == 10
        assert len(set(chosen)) == 10

    def test_10_scene_simulation_engine_resolve(self, isolated_engine: LoopVideoEngine):
        """
        Simulate a 10-scene longform video through LoopVideoEngine.resolve_loop_video.
        Verify that 10 distinct file paths are chosen.
        """
        chosen_paths: List[Path] = []
        chosen_ids: List[str] = []

        for scene_idx in range(10):
            path = isolated_engine.resolve_loop_video(
                category="horror",
                orientation="horizontal",
                seed=scene_idx + 10,
                channel="moku",
                exclude_loop_ids=chosen_ids,
            )
            assert path.is_file()
            assert path not in chosen_paths, f"Engine repeated file path at scene {scene_idx}: {path}"
            chosen_paths.append(path)
            # Find loop_id corresponding to this path to append to exclude_loop_ids
            matching = [l for l in isolated_engine.catalog.list_loops(limit=200) if Path(l.file_path).name == path.name]
            if matching:
                chosen_ids.append(matching[0].loop_id)
            else:
                chosen_ids.append(path.stem)

        assert len(chosen_paths) == 10
        assert len(set(chosen_paths)) == 10

    def test_graceful_catalog_exhaustion(self, isolated_catalog: LoopCatalogRepository):
        """
        Verify that when candidate loops are completely exhausted in exclude_loop_ids,
        the catalog gracefully returns None rather than raising an exception.
        """
        # Collect all vertical moku loop IDs (6 total)
        moku_v_loops = [
            l.loop_id for l in isolated_catalog.list_loops(limit=200)
            if l.orientation == "vertical" and l.channel == "moku"
        ]
        assert len(moku_v_loops) > 0

        # Pass all of them in exclude_loop_ids
        result = isolated_catalog.get_best_loop(
            category="horror",
            orientation="vertical",
            channel="moku",
            exclude_loop_ids=moku_v_loops,
        )
        assert result is None, f"Expected None when all candidates are excluded, got: {result}"


class TestCategoryAliases:
    """Challenge Dimension 4: Category Aliasing & Semantic Mapping."""

    TEST_ALIASES = [
        "tactical_chamber",
        "bunker",
        "containment",
        "chamber",
        "corridor",
        "asylum",
        "morgue",
        "facility",
        "scp",
        "haunted_house",
        "creepy_woods",
        "misty_pines",
        "cabin",
        "cemetery",
        "cozy_hearth",
        "reddit_aita",
        "aita",
        "drama_aita",
        "confession",
        "relationships",
        "family_drama",
        "cozy_interior",
        "warm_hearth",
        "cyberpunk",
    ]

    def test_alias_count_exceeds_minimum(self):
        """Verify at least 20 aliases are defined and tested."""
        assert len(self.TEST_ALIASES) >= 20, f"Expected >= 20 aliases, got {len(self.TEST_ALIASES)}"

    @pytest.mark.parametrize("alias", TEST_ALIASES)
    def test_alias_horizontal_resolves_valid_physical_video(self, isolated_engine: LoopVideoEngine, alias: str):
        """
        Verify each alias resolves to a valid, existing, non-empty physical video loop
        for horizontal orientation (16:9).
        """
        path = isolated_engine.resolve_loop_video(category=alias, orientation="horizontal")
        assert isinstance(path, Path)
        assert path.is_file(), f"Alias '{alias}' resolved to nonexistent path: {path}"
        assert path.stat().st_size >= 25_000, f"Alias '{alias}' resolved to undersized file (<25KB): {path}"
        assert path.suffix.lower() in (".mp4", ".webm"), f"Alias '{alias}' resolved to unexpected format: {path}"
        assert path.name not in isolated_engine.SYNTHETIC_MONOCHROME_FILES, (
            f"Alias '{alias}' resolved to banned monochrome file: {path.name}"
        )

    @pytest.mark.parametrize("alias", TEST_ALIASES)
    def test_alias_vertical_resolves_valid_physical_video(self, isolated_engine: LoopVideoEngine, alias: str):
        """
        Verify each alias resolves to a valid physical video loop for vertical orientation (9:16).
        """
        path = isolated_engine.resolve_loop_video(category=alias, orientation="vertical")
        assert isinstance(path, Path)
        assert path.is_file(), f"Alias '{alias}' (vertical) resolved to nonexistent path: {path}"
        assert path.stat().st_size >= 25_000, f"Alias '{alias}' (vertical) file too small: {path}"
        assert path.name not in isolated_engine.SYNTHETIC_MONOCHROME_FILES

    def test_alias_normalization_canonical_categories(self, isolated_engine: LoopVideoEngine):
        """Verify normalize_category maps aliases to expected canonical categories."""
        expected_mappings = {
            "tactical_chamber": "horror",
            "bunker": "horror",
            "containment": "horror",
            "creepy_woods": "dark_forest",
            "cozy_hearth": "drama",
            "reddit_aita": "drama",
            "cozy_interior": "cozy_ambient",
            "cyberpunk": "scifi",
            "deep_space": "space_abyss",
        }
        for alias, expected_cat in expected_mappings.items():
            norm = isolated_engine.normalize_category(alias)
            assert norm == expected_cat, f"Expected alias '{alias}' to map to '{expected_cat}', got '{norm}'"


class TestSyntheticMonochromePurge:
    """Challenge Dimension 5: Synthetic Monochrome Loop Exclusion."""

    def test_monochrome_loops_never_returned_in_regular_queries(self, isolated_catalog: LoopCatalogRepository):
        """
        Verify that across 100 queries with varied categories and orientations,
        banned synthetic monochrome loops are NEVER returned.
        """
        banned_ids = SYNTHETIC_MONOCHROME_LOOP_IDS
        categories = ["horror", "drama", "scifi", "dark_forest", "dark_ambient", "cozy_ambient"]

        for i in range(100):
            cat = categories[i % len(categories)]
            orient = "horizontal" if i % 2 == 0 else "vertical"
            loop = isolated_catalog.get_best_loop(
                category=cat,
                orientation=orient,
                seed=i * 53 + 1,
            )
            assert loop is not None
            assert loop.loop_id not in banned_ids, (
                f"Query {i} returned banned synthetic monochrome loop: {loop.loop_id}"
            )
            assert loop.technology != "ffmpeg_lavfi", f"Query {i} returned ffmpeg_lavfi synthetic loop: {loop.loop_id}"
            assert loop.sha256 != "procedural", f"Query {i} returned procedural loop: {loop.loop_id}"


class TestProductionDatabaseSanity:
    """Challenge Dimension 6: Verify Production Database Integrity."""

    def test_production_db_loop_counts(self, production_catalog: LoopCatalogRepository):
        """Verify that DEFAULT_DB_PATH contains >= 50 loops with 0 synthetic monochrome loops."""

        if production_catalog.count_loops() < 50:
            pytest.skip("DEFAULT_DB_PATH has no production loop catalog in this checkout")
        total = production_catalog.count_loops()
        assert total >= 50, f"Expected >=50 loops in production database, found {total}"

        stats = production_catalog.get_stats()
        assert stats["total_loops"] >= 50
        assert stats["by_orientation"]["horizontal"] >= 30
        assert stats["by_orientation"]["vertical"] >= 10

        # Verify no monochrome IDs in production database
        all_ids = [l.loop_id for l in production_catalog.list_loops(limit=200)]
        for banned in SYNTHETIC_MONOCHROME_LOOP_IDS:
            assert banned not in all_ids, f"Banned loop {banned} found in production database!"
