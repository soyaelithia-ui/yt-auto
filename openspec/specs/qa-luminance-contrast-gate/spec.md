# Capability: QA Perceived Luminance and Low-Contrast Shadow Gate

## Requirements

### Requirement: Average Perceived Luminance Floor
The QA subsystem MUST calculate the mean perceived photometric luminance across sampled video frames and reject deliveries that fall below the minimum human visibility floor.

#### Scenario: Rejection of near pitch-black frames with minor center glow
- **Given** a sequence of sampled video frames where 95% of pixel surface is black ($Y < 16$) and center light cone mean luminance is $Y = 18$
- **When** the `LuminanceContrastGate` evaluates the sampled frames with threshold $Y_{\text{min}} = 22.0$
- **Then** the gate result MUST return `is_passed = False`
- **And** the failure code MUST be `ERR_QA_UNDER_ILLUMINATED_SCENE`
- **And** the message MUST report insufficient overall scene luminance.

#### Scenario: Acceptance of well-lit cinematic chiaroscuro frames
- **Given** a sequence of sampled video frames from a horror production with warm fire highlights ($Y_{\text{mean}} \ge 35.0$) and high edge density
- **When** the `LuminanceContrastGate` evaluates the sampled frames
- **Then** the gate result MUST return `is_passed = True`
- **And** the code MUST be `OK_LUMINANCE_COMPLIANT`.
