# Spec Delta: Semantic Scenic Visual Intelligence & Maritime Lighthouse Engine

## Requirements

### Requirement: Multi-Layer Procedural Atmospheric Shaders
The visual engine SHALL support 9 canonical procedural WGSL shader archetypes (`tactical_chamber`, `dark_forest`, `arctic_desolation`, `cosmic_singularity`, `arcade_vector_flight`, `parkour_runner`, `cozy_hearth`, `synaptic_network`, `maritime_lighthouse`).
The `maritime_lighthouse` shader SHALL render:
- Celestial night sky with cratered moon and soft radial halo.
- Multi-frequency undulating ocean waves with specular moon reflections.
- Rocky coastal headland cliff with tapered lighthouse tower and lantern gallery.
- Volumetric 360-degree rotating light beam with atmospheric mist scattering.

#### Scenario: Maritime Narrative Shader Compilation
- GIVEN a story mentioning coastal cliffs or lighthouses
- WHEN the procedural loop engine resolves the video
- THEN `maritime_lighthouse.wgsl` compiles on Mesa Lavapipe without errors and produces valid RGBA frames.

### Requirement: Setting-Adaptive Thumbnail Composition
The `ThumbnailEngine` and `AdaptiveSubjectCompositor` SHALL composite setting-accurate anatomical and architectural silhouettes matching the detected narrative archetype without duplicating background celestial or structural elements.

#### Scenario: Coastal Story Thumbnail Generation
- GIVEN a story set at a lighthouse or sea cliff
- WHEN a thumbnail is generated
- THEN the compositor places a solitary coastal observer with lantern on the cliff ledge overlooking the sea with accent rim lighting.
