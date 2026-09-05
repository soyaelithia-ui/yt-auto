# Delta for Editorial and Content Policy

## MODIFIED Requirements

### Requirement: Anti-Filler Pure Procedural Visuals
All background visuals in production renders MUST be generated through FFmpeg procedural loops (lavfi/catalog). Static stock photographs and generic filler images are strictly prohibited (`DISCARDED_GENERIC_FILLER`). WebGL, Three.js, and HTML5 Canvas MUST NOT be the production background stack. Emblems, agency badges, and institutional marks MUST be projected as vector overlays or dynamic HUD elements respecting visual margins.
(Previously: Production backgrounds MUST be generated through procedural WebGL, Three.js, or HTML5 Canvas.)

#### Scenario: Visual Quality Audit
- **Given** a generated scene manifest `SceneManifestV2`
- **When** the `ImageAuditorAgent` inspects visual assets
- **Then** static stock photos MUST be rejected
- **And** FFmpeg procedural loops or official vector insignia overlays MUST be approved
- **And** WebGL, Three.js, or HTML5 Canvas MUST NOT be required for approval.

#### Scenario: Generic filler still discarded (Edge Case)
- **Given** a scene whose only background candidate is a static stock photograph
- **When** the `ImageAuditorAgent` inspects visual assets
- **Then** the asset MUST be classified `DISCARDED_GENERIC_FILLER`
- **And** the pipeline MUST NOT approve WebGL, Three.js, or Canvas as a substitute production background.
