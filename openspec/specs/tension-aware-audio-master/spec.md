# Specification: Tension-Aware Audio Master

## Capability Overview
The `tension-aware-audio-master` capability governs the multi-track audio generation, dynamic sidechain ducking, tension-coupled procedural synthesizer modulation, sample-accurate sound effects (SFX) placement, and broadcast EBU R128 loudness mastering across video production pipelines.

## Requirements

### Requirement 1: Dynamic Sidechain Compression and Ducking
The audio mixer MUST implement sidechain compression where narration voice splits into primary vocal and sidechain control streams. When voice activity is detected, the mixer MUST dynamically attenuate background drone and ambience tracks by at least $-18\text{ dB}$ (compression ratio $\ge 5:1$, attack time $10\text{ms} \le t_{\text{attack}} \le 20\text{ms}$, release time $250\text{ms} \le t_{\text{release}} \le 400\text{ms}$).

#### Scenario: Background drone ducking during voiceover narration (Happy Path)
- **Given** an active voiceover track and a continuous procedural sub-drone bed
- **When** the FFmpeg `sidechaincompress` filter executes during voice playback
- **Then** the drone bed gain MUST drop by $-18\text{ dB}$ relative to nominal amplitude
- **And** within $350\text{ms}$ following voice pauses, the drone bed MUST smoothly return to nominal gain without audible pumping.

#### Scenario: Continuous voiceover without vocal pauses (Edge Case)
- **Given** an unbroken monologue lasting 45 seconds without pauses
- **When** the sidechain compressor processes the stream
- **Then** the background audio MUST remain stably compressed at the target ducking floor
- **And** the compressor MUST NOT exhibit gain chatter or sudden amplification spikes.

### Requirement 2: Broadcast EBU R128 Loudness Compliance
The audio master engine MUST normalize the final multi-track mixdown to strict EBU R128 broadcast standards using the FFmpeg `loudnorm` filter with parameters:
- Integrated Loudness target: $I = -14.0\text{ LUFS} \pm 0.5\text{ LUFS}$
- Maximum True Peak: $TP \le -1.5\text{ dBTP}$
- Maximum Loudness Range: $LRA \le 11.0\text{ LU}$

#### Scenario: Final audio master meets EBU R128 broadcast targets (Happy Path)
- **Given** a composite multi-track audio mix containing voice, drone, and SFX
- **When** the EBU R128 `loudnorm` mastering pass executes
- **Then** the resulting master audio file MUST measure $I = -14.0 \pm 0.5\text{ LUFS}$
- **And** the peak amplitude MUST NOT exceed $-1.5\text{ dBTP}$
- **And** the audio stream MUST NOT contain digital clipping distortion or sample overflow.

#### Scenario: Low-amplitude input audio with high dynamic range (Edge Case)
- **Given** a quiet whisper vocal track with peak levels below $-30\text{ dBFS}$
- **When** `loudnorm` processing runs
- **Then** the normalization filter MUST boost the integrated loudness to $-14.0\text{ LUFS}$
- **And** the noise floor amplification MUST be bounded to prevent excessive hiss amplification.

### Requirement 3: Tension-Coupled Procedural Sub-Drone Bed
The audio engine MUST synthesize procedural multi-oscillator sub-bass and harmonic drone beds where the fundamental oscillator frequency ($28\text{Hz} \le f_0 \le 65\text{Hz}$) and harmonic saturation dynamically modulate according to the narrative tension score ($T \in [1, 5]$).

#### Scenario: Drone frequency and harmonic modulation across tension phases (Happy Path)
- **Given** an audio contract with base frequency $34.0\text{Hz}$ and tension escalation to level 5
- **When** `ProceduralDroneSynthesizer` generates the drone WAV track
- **Then** the generator MUST modulate harmonic overtones and sub-bass resonance corresponding to tension level 5
- **And** the output waveform MUST maintain phase continuity without zero-crossing click artifacts.

#### Scenario: Abrupt scene tension step transitions (Edge Case)
- **Given** a sharp tension transition from level 1 to level 5 across adjacent scene boundaries
- **When** the drone synthesizer constructs the timeline
- **Then** the engine MUST apply a linear or cosine crossfade ramp ($\ge 0.5\text{s}$) between frequency presets
- **And** the resulting audio stream MUST NOT produce transient pops or discontinuity clicks.

### Requirement 4: Sample-Accurate Inter-Act Transition SFX Orchestration
The audio mixer MUST position thematic SFX cues (risers, sub-drops, hydrophone clicks, radar sweeps) at sample-accurate millisecond offsets synchronized with visual scene crossfades using FFmpeg `adelay` and `amix`.

#### Scenario: Inter-act riser and sub-drop SFX insertion (Happy Path)
- **Given** an SFX timeline with a riser cue at $t = 11.25\text{s}$ matching a scene crossfade
- **When** `CosmicAudioMixer._build_sfx_track` compiles the SFX timeline
- **Then** the SFX cue MUST be delayed by exactly $11250\text{ms}$
- **And** the mixed audio master MUST align the SFX peak energy with the visual scene boundary.

#### Scenario: Missing or unresolvable SFX asset identifier (Edge Case)
- **Given** an SFX cue with an unknown identifier `"UNKNOWN_SFX_99"`
- **When** SFX track compilation executes
- **Then** the synthesizer MUST generate a procedural fallback sine/noise sweep
- **And** the mixer MUST complete master audio compilation without raising `FileNotFoundError`.
