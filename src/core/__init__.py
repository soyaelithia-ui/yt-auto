"""Core domain, repository, provider, quality, contracts, and scheduler subsystems."""


def __getattr__(name: str):
    if name in (
        "ClaimedLeaseContext",
        "PipelineContext",
        "RenderSpec",
        "ReviewContract",
        "RunContext",
        "StoryRecord",
    ):
        import src.core.contracts as contracts
        return getattr(contracts, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ClaimedLeaseContext",
    "PipelineContext",
    "RenderSpec",
    "ReviewContract",
    "RunContext",
    "StoryRecord",
]
