# Delta for Editorial and Content Governance Policy

## MODIFIED Requirements

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
