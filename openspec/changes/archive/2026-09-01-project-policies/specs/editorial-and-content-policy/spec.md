# Spec: Editorial and Content Governance Policy

## Requirement: AI-First Semantic Curation and Fail-Closed Behavior
The system MUST execute all narrative curation, translation, and SEO metadata generation exclusively through native LLM agents (`gemini-3.8-flash-high` exclusive) under the `agy` CLI harness. When LLM provider quota is exhausted or circuit breakers open, the pipeline MUST fail closed with `AIProviderChainExhausted` rather than falling back to low-quality deterministic dummy scripts.

### Scenario: LLM Quota Exhaustion Fails Closed
- **Given** a story in state `CLAIMED`
- **When** all LLM providers in the chain fail or trip their circuit breakers
- **Then** the curation stage MUST raise `AIProviderChainExhausted`
- **And** the story state MUST transition to `RETRYABLE_FAILED` with an exponential backoff cooling period.

## Requirement: Anti-Filler Pure Procedural Visuals
All background visuals in production renders MUST be generated through procedural WebGL, Three.js, or HTML5 Canvas code. Static stock photographs and generic filler images are strictly prohibited (`DISCARDED_GENERIC_FILLER`). Emblems, agency badges, and institutional marks MUST be projected as vector overlays or dynamic HUD elements respecting visual margins.

### Scenario: Visual Quality Audit
- **Given** a generated scene manifest `SceneManifestV2`
- **When** the `ImageAuditorAgent` inspects visual assets
- **Then** static stock photos MUST be rejected
- **And** procedural shader loops or official vector insignia overlays MUST be approved.

## Requirement: SCP Lore Ingestion and Creative Commons Attribution
When curating SCP Foundation anomalies or derivative horror fiction, the system MUST embed proper Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0) credits in video metadata and pinned comments, explicitly identifying the original author, SCP item number, and wiki source URL.

### Scenario: SCP Attribution Metadata
- **Given** a story scraped from the SCP Foundation wiki
- **When** the SEO and publication metadata are generated
- **Then** the YouTube description and pinned comment MUST contain canonical CC BY-SA 3.0 license declarations with author and article attribution.
