# Specification: Pinned Comment Lifecycle & Failure Marking

## Purpose
The `pinned-comment-lifecycle` capability dispatches AI-generated pinned comments to YouTube immediately following video publication, attempts to pin the comment, catches any execution errors gracefully, and records the exact status (`posted`, `failed`, `disabled`) into the publication record.

## Requirements

### Requirement 1: Comment Thread Insertion & Pinning
When a video is published and a `pinned_comment` is provided by the AI packaging agent, the system MUST call `youtube.commentThreads().insert` to post the comment under the newly uploaded video.

#### Scenario: Successful pinned comment post (Happy Path)
- **Given** a published video ID `"vid123"` and a pinned comment text `"👇 ¿Qué habrías hecho tú?"`
- **When** `post_pinned_comment()` is executed with valid channel credentials
- **Then** YouTube creates the top-level comment thread
- **And** `publications.comment_status` MUST be set to `"posted"`
- **And** `publications.pinned_comment` MUST store the posted text.

### Requirement 2: Graceful Error Interception & Failure Marking
If comment posting fails due to comments being disabled, permission errors, network failure, or API quota exhaustion:
- The system MUST NOT raise an uncaught exception or abort the publication transaction.
- The system MUST record `comment_status = "failed"` in SQLite `publications`.
- The system MUST record the error explanation in `publications.comment_error`.

#### Scenario: Comments disabled on YouTube video marks failure gracefully (Edge Case)
- **Given** a published video where YouTube comments are disabled by channel policy or age restriction
- **When** `post_pinned_comment()` receives an error with reason `"commentsDisabled"`
- **Then** the function returns a failure outcome without crashing
- **And** `publications.comment_status` is updated to `"failed"`
- **And** `publications.comment_error` contains `"commentsDisabled"`.
