# Spec: Editorial and Content Governance Policy

## Requirements

### Requirement: AI-First Semantic Curation and Fail-Closed Behavior
The system MUST execute all narrative curation, translation, and SEO metadata generation primarily through native LLM agents (`google.antigravity.Agent` using `gemini-3.8-flash-high` or configured Gemini models). When LLM provider quota is exhausted (`RESOURCE_EXHAUSTED` / HTTP 429), saturation errors occur, or agent circuit breakers open, the pipeline MUST NOT fail closed or terminate daemon workers with fatal exceptions. Instead, the pipeline MUST gracefully fall back to vetted procedural narrative templates (from `src/templates/` and `src/curators/`) and deterministic algorithmic SEO formulas (`_deterministic_seo(topic, fmt, niche)`), tripping the circuit breaker and logging the saturation event while allowing continuous scheduled video production to proceed uninterrupted.
(Previously: The system enforced strict fail-closed behavior with AIProviderChainExhausted upon quota exhaustion or circuit breaker activation, halting daemon workers instead of allowing procedural/deterministic fallback.)

#### Scenario: Primary AI-First Curation Under Nominal Conditions (Happy Path)
- **Given** a story in state `CLAIMED` and active LLM provider quota
- **When** the narrative curation and SEO optimization stages execute
- **Then** narrative curation, translation, and SEO metadata generation MUST be executed via the native LLM agent
- **And** procedural fallback templates MUST NOT be utilized.

#### Scenario: Graceful Fallback on LLM Quota Exhaustion or Open Circuit Breaker (Modified Scenario)
- **Given** a story in state `CLAIMED`
- **When** all LLM providers return `RESOURCE_EXHAUSTED` (HTTP 429), raise `AgentSaturationError`, or trip the agent `CircuitBreaker`
- **Then** the curation stage MUST gracefully fall back to vetted procedural narrative templates
- **And** the SEO stage MUST fall back to deterministic metadata formulas (`_deterministic_seo`)
- **And** the pipeline MUST NOT raise an unhandled `AIProviderChainExhausted` or abort daemon execution
- **And** the story MUST continue processing through video rendering, mastering, and publishing.

#### Scenario: Fallback Narrative and Metadata Schema Compliance (Edge Case)
- **Given** narrative and SEO generation operating under procedural fallback mode
- **When** the fallback story and metadata are assembled
- **Then** the narrative text MUST comply with channel target duration and niche tone constraints
- **And** the generated metadata MUST contain valid channel-compliant titles, descriptions, and tags conforming to the channel schema without placeholder or empty values.

#### Scenario: Circuit Breaker Reset and Return to AI Curation (Edge Case)
- **Given** an open circuit breaker triggered by preceding quota exhaustion
- **When** the circuit breaker cooldown period (300 seconds) expires and a subsequent story is claimed
- **Then** the curation stage MUST attempt native LLM agent execution
- **And** if successful, the circuit breaker MUST reset to closed state.

### Requirement: Anti-Filler Pure Procedural Visuals
Production video backgrounds MUST come from FFmpeg procedural loops (lavfi/catalog) or curated **clean** scenery (no baked title/warning/CRT/UI text). Generic stock filler and pre-baked title cards are prohibited (`DISCARDED_GENERIC_FILLER`). WebGL, Three.js, and HTML5 Canvas MUST NOT be the production background stack. Emblems and agency marks MUST be vector overlays / dynamic HUD (thumbnail composition path for text chrome). Authoritative classification: `docs/visual-assets-policy.md`.

#### Scenario: Visual Quality Audit
- **Given** a generated scene manifest `SceneManifestV2`
- **When** the `ImageAuditorAgent` inspects visual assets
- **Then** generic stock photos and baked title cards MUST be rejected
- **And** FFmpeg loops, clean scenery, or official vector insignia overlays MUST be approved
- **And** WebGL, Three.js, or HTML5 Canvas MUST NOT be required for approval.

#### Scenario: Generic filler still discarded (Edge Case)
- **Given** a scene whose only background candidate is a static stock photograph or quarantined title card
- **When** the `ImageAuditorAgent` inspects visual assets
- **Then** the asset MUST be classified `DISCARDED_GENERIC_FILLER`
- **And** the pipeline MUST NOT approve WebGL, Three.js, or Canvas as a substitute production background.

### Requirement: SCP Lore Ingestion and Creative Commons Attribution
When curating SCP Foundation anomalies or derivative horror fiction, the system MUST embed proper Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0) credits in video metadata and pinned comments, explicitly identifying the original author, SCP item number, and wiki source URL.

#### Scenario: SCP Attribution Metadata
- **Given** a story scraped from the SCP Foundation wiki
- **When** the SEO and publication metadata are generated
- **Then** the YouTube description and pinned comment MUST contain canonical CC BY-SA 3.0 license declarations with author and article attribution.
