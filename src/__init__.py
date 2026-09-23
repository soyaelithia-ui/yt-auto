# YouTube Automation System - Core Package


def __getattr__(name: str):
    if name == "youtube_control":
        from src.youtube import control
        return control
    if name == "youtube_uploader":
        from src.youtube import uploader
        return uploader
    if name == "review_publication_adapter":
        from src import review_adapter
        return review_adapter
    if name == "youtube_auth":
        from src.youtube import auth
        return auth
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "youtube_control",
    "youtube_uploader",
    "review_publication_adapter",
    "youtube_auth",
]
