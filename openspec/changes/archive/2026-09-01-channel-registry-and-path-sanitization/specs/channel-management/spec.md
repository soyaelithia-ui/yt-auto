# Specification: Dynamic Channel Management

## Capability Overview
The `channel-management` capability provides declarative and dynamic channel resolution across the CLI, pipeline, queue scheduler, and uploader adapters without hardcoding channel identifiers into static enums.

## Requirements

### Requirement 1: Dynamic Channel Resolution
The domain resolver `canonical_channel()` MUST query the dynamic `ChannelProfileRegistry` to validate any channel registered under `config/channels/*.json`.

#### Scenario: Resolving standard configured channels (Happy Path)
- **Given** active channel profiles for `moku`, `aelithia`, and `scifi` in `config/channels/`
- **When** `canonical_channel("scifi")` or `canonical_channel("moku")` is invoked
- **Then** the resolver MUST return a valid string identifier matching the normalized channel ID.

#### Scenario: Resolving legacy channel aliases (Backward Compatibility)
- **Given** legacy channel aliases `terror`, `scp`, `aita`, `soy_el_malo`, `drama`
- **When** `canonical_channel("terror")` or `canonical_channel("aita")` is invoked
- **Then** the resolver MUST map `terror` to `moku` and `aita` to `aelithia`.

#### Scenario: Rejecting unregistered or unknown channels (Error State)
- **Given** an unregistered channel string `unknown_channel_99`
- **When** `canonical_channel("unknown_channel_99")` is invoked
- **Then** the resolver MUST raise a `ValueError` indicating the channel is unknown.

### Requirement 2: Dynamic Runtime Settings Lookup
The `RuntimeSettings.channel()` method MUST retrieve `ChannelSettings` dynamically from `ChannelProfileRegistry` when a channel is not present in the initial static dict.

#### Scenario: Fetching ChannelSettings for non-default channel (Happy Path)
- **Given** a valid `RuntimeSettings` instance and channel profile `scifi.json`
- **When** `runtime_settings.channel("scifi")` is invoked
- **Then** the returned `ChannelSettings` object MUST contain typography, design, auth, and voice parameters configured in `config/channels/scifi.json`.
