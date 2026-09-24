# Specification: Native Automatic Link Collection

## Purpose
The `automatic-link-collection` capability enables autonomous, complete crawling of channel uploads on YouTube, extracting canonical URLs, short URLs, and Shorts URLs, and updating the local SQLite inventory.

## Requirements

### Requirement 1: Comprehensive Uploads Crawling
The link collection engine MUST page through the channel's uploads playlist on YouTube Data API v3 until all available public and unlisted videos are harvested (`max_items <= 0` fetches 100% of uploads).

#### Scenario: Channel with 40 videos is 100% collected without truncation (Happy Path)
- **Given** an authenticated YouTube channel with 40 published videos
- **When** `collect_channel_links(channel="horror", max_items=0)` is called
- **Then** the result `synced_count` MUST equal 40
- **And** all 40 records MUST exist in the SQLite `publications` table.

### Requirement 2: Multi-Format URL Derivation
For each collected video, the engine MUST construct and make available:
- Canonical Watch URL: `https://www.youtube.com/watch?v={video_id}`
- Short URL: `https://youtu.be/{video_id}`
- Shorts URL: `https://www.youtube.com/shorts/{video_id}`

#### Scenario: Derivation of URL formats
- **Given** a video ID `"abc123xyz89"`
- **When** URL variants are requested
- **Then** the watch URL MUST be `"https://www.youtube.com/watch?v=abc123xyz89"`
- **And** the short URL MUST be `"https://youtu.be/abc123xyz89"`
- **And** the shorts URL MUST be `"https://www.youtube.com/shorts/abc123xyz89"`.

### Requirement 3: Automated Daemon Maintenance Integration
The link collector MUST be executed automatically during the periodic 24h daemon maintenance sweep without requiring manual operator intervention.
