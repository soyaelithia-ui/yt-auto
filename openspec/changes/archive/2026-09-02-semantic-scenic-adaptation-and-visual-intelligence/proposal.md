# Proposal: Semantic Scenic Visual Intelligence & Setting Adaptation

## Motivation
Currently, visual loop selection frequently falls back to `arctic_desolation` (the snowy mountain with SCP-096 entity) regardless of story narrative (e.g., an underground abandoned subway station story received the arctic blizzard loop with SCP silhouette). The system needs comprehensive semantic scene detection, intelligent LLM setting classification, and dynamic procedural setting composition so every story receives contextually accurate visual backgrounds and matching thumbnail art.

## Goals
1. **Intelligent Semantic Setting Classifier (`src/core/scenic_detector.py`)**:
   - Classify story narrative and topic across all 8 native procedural archetypes (`tactical_chamber`, `dark_forest`, `arctic_desolation`, `cosmic_singularity`, `arcade_vector_flight`, `parkour_runner`, `cozy_hearth`, `synaptic_network`).
   - Add deep keyword dictionaries and regex patterns for underground stations, subways, tunnels, bunkers, haunted woods, sci-fi voids, cozy domestic interiors, and retro arcade gameplay.
   - Support zero-shot LLM setting inference fallback when heuristic confidence is low.
2. **Dynamic Archetype Mapping & Catalog Routing (`src/media/loop_engine.py` & `src/core/catalog.py`)**:
   - Ensure catalog queries match semantic tags and archetype affinities before falling back.
   - Prevent arbitrary fallback to `arctic_desolation` when a story belongs to an underground, urban, or domestic setting.
3. **Adaptive Thumbnail Subject & Environment Compositor (`src/media/thumbnails/subject_extractor.py`)**:
   - Render setting-appropriate subject silhouettes and environmental elements (e.g., underground tunnel portal / staircase silhouette for subway/bunker stories; forest trees for dark woods; solitary coat for drama; astronaut for space).
