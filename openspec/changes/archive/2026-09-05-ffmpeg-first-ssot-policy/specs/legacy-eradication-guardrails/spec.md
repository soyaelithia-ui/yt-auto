# Delta for Legacy Eradication Guardrails

## MODIFIED Requirements

### Requirement: Truthful SDD Context Configuration
The SDD context in `openspec/config.yaml` SHALL reflect only active production dependencies. Production media stack SHALL list FFmpeg and MAY list Pillow for thumbnail SSOT. The context SHALL NOT list Playwright as production media. The context SHALL NOT list wgpu-py or resvg-py as the production stack.
(Previously: Context SHALL NOT list Playwright or Pillow as the production media stack.)

#### Scenario: OpenSpec tech stack validation
- **Given** `openspec/config.yaml`
- **When** the `context:` block is parsed
- **Then** Playwright SHALL NOT be declared as part of the production media stack
- **And** wgpu-py and resvg-py SHALL NOT be declared as the production stack
- **And** Pillow MAY be declared for thumbnail SSOT.

#### Scenario: Pillow thumbs SSOT is not a retired library (Edge Case)
- **Given** thumbnail generation uses Pillow as SSOT
- **When** the `context:` block is validated against this guardrail
- **Then** listing Pillow for thumbs SHALL be allowed
- **And** Playwright SHALL remain forbidden as production media.
