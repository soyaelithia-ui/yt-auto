# Spec: Editorial and Content Governance Policy

## Requirement: AI-First Semantic Curation and Fail-Closed Behavior
The system MUST execute all narrative curation, translation, and SEO metadata generation exclusively through native LLM agents (`gemini-3.8-flash-high` primary, `gemini-3.7-flash` / `gemini-3.6-flash` secondary) under the `agy` CLI harness. When LLM provider quota is exhausted or circuit breakers open, the pipeline MUST fail closed with `AIProviderChainExhausted` rather than falling back to low-quality deterministic dummy scripts.

### Scenario: LLM Quota Exhaustion Fails Closed
- **Given** a story in state `CLAIMED`
- **When** all LLM providers in the chain fail or trip their circuit breakers
- **Then** the curation stage MUST raise `AIProviderChainExhausted`
- **And** the story state MUST transition to `RETRYABLE_FAILED` with an exponential backoff cooling period.

## Requirement: Anti-Filler Pure Procedural Visuals
All background visuals in production renders MUST be generated through FFmpeg procedural loops (lavfi/catalog). Static stock photographs and generic filler images are strictly prohibited (`DISCARDED_GENERIC_FILLER`). WebGL, Three.js, and HTML5 Canvas MUST NOT be the production background stack. Emblems, agency badges, and institutional marks MUST be projected as vector overlays or dynamic HUD elements respecting visual margins.

### Scenario: Visual Quality Audit
- **Given** a generated scene manifest `SceneManifestV2`
- **When** the `ImageAuditorAgent` inspects visual assets
- **Then** static stock photos MUST be rejected
- **And** FFmpeg procedural loops or official vector insignia overlays MUST be approved
- **And** WebGL, Three.js, or HTML5 Canvas MUST NOT be required for approval.

### Scenario: Generic filler still discarded (Edge Case)
- **Given** a scene whose only background candidate is a static stock photograph
- **When** the `ImageAuditorAgent` inspects visual assets
- **Then** the asset MUST be classified `DISCARDED_GENERIC_FILLER`
- **And** the pipeline MUST NOT approve WebGL, Three.js, or Canvas as a substitute production background.

## Requirement: SCP Lore Ingestion and Creative Commons Attribution
When curating SCP Foundation anomalies or derivative horror fiction, the system MUST embed proper Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0) credits in video metadata and pinned comments, explicitly identifying the original author, SCP item number, and wiki source URL.

### Scenario: SCP Attribution Metadata
- **Given** a story scraped from the SCP Foundation wiki
- **When** the SEO and publication metadata are generated
- **Then** the YouTube description and pinned comment MUST contain canonical CC BY-SA 3.0 license declarations with author and article attribution.
