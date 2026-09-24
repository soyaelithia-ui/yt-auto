# Specification: AI-Native Story Packaging & Elimination of Boilerplate Templates

## Purpose
The `ai-native-story-packaging` capability completely eliminates rigid, deterministic string concatenation and template-based titles and descriptions. The AI optimizer generates 100% of the YouTube packaging metadata (viral title, engaging description with narrative synopsis and natural CTAs, tailored tags, and discussion-sparking pinned comment) directly from the full story script and channel voice.

## Requirements

### Requirement 1: Full Story Context Ingestion
The AI packaging agent (`SeoOptimizerAgent`) MUST accept the full story script text, synopsis, target format, and channel editorial tone, rather than evaluating only a raw title string.

#### Scenario: Metadata generated using rich narrative context
- **Given** a story with title `"The Red Staircase"`, a 300-word horror script, and lane `"horror"`
- **When** `SeoOptimizerAgent.optimize()` is invoked with narrative context
- **Then** the prompt to the AI agent MUST include the story synopsis and script context
- **And** the generated description MUST reflect story-specific plot elements rather than generic boilerplate.

### Requirement 2: Elimination of Hardcoded Title and Description Templates
`stage_11_metadata.py` MUST NOT call hardcoded string concatenation templates (`generate_description()`, `generate_title()`) to construct the final published metadata. All metadata fields (`title`, `description`, `tags`, `hashtags`, `pinned_comment`) MUST come from the AI optimizer's intelligent structured output.

#### Scenario: Pipeline metadata stage applies AI output directly
- **Given** an AI optimizer response containing `selected_title`, `description`, `tags`, and `pinned_comment`
- **When** `stage_11_thumbnail_metadata` executes
- **Then** `ctx.youtube_title` is assigned the AI-generated `selected_title`
- **And** `ctx.youtube_description` is assigned the AI-generated `description`
- **And** `ctx.pinned_comment` is assigned the AI-generated `pinned_comment`
- **And** no rigid template headers (e.g. `"💭 Título | Historias Reales y Confesiones en..."`) are injected.
