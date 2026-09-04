"""Parse live FFmpeg argv evidence for stream-copy vs veryfast/CRF 21.

Does not spawn ffmpeg. Input paths are read as UTF-8 text only.
"""

from __future__ import annotations

import json
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union


@dataclass(frozen=True)
class HotPathVerdict:
    copy_observed: bool
    reencode_observed: bool
    reencode_preset: Optional[str]
    reencode_crf: Optional[int]
    argv_recovered: bool
    passed: bool
    note: str


def read_evidence_file(path: Union[str, Path]) -> str:
    """Read a capture as UTF-8 data. Missing files yield empty text (fail closed)."""
    target = Path(path)
    try:
        return target.read_text(encoding="utf-8")
    except OSError:
        return ""


def _flag_value(tokens: Sequence[str], flag: str) -> Optional[str]:
    for i, tok in enumerate(tokens):
        if tok == flag and i + 1 < len(tokens):
            return tokens[i + 1]
    return None


def _extract_argvs(text: str) -> list[list[str]]:
    argvs: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if "ffmpeg" not in line or "-c:v" not in line:
            continue
        if "command:" in line:
            line = line.split("command:", 1)[1].strip()
        try:
            tokens = shlex.split(line)
        except ValueError:
            tokens = line.split()
        if not tokens:
            continue
        if tokens[0] != "ffmpeg":
            try:
                idx = tokens.index("ffmpeg")
            except ValueError:
                continue
            tokens = tokens[idx:]
        argvs.append(tokens)
    return argvs


def parse_ffmpeg_evidence(text: str) -> HotPathVerdict:
    argvs = _extract_argvs(text)
    if not argvs:
        return HotPathVerdict(
            copy_observed=False,
            reencode_observed=False,
            reencode_preset=None,
            reencode_crf=None,
            argv_recovered=False,
            passed=False,
            note="missing argv",
        )

    copy_observed = False
    reencode_observed = False
    presets: list[str] = []
    crfs: list[int] = []

    for tokens in argvs:
        codec = _flag_value(tokens, "-c:v")
        if codec == "copy":
            copy_observed = True
        if codec == "libx264" or "libx264" in tokens:
            reencode_observed = True
            preset = _flag_value(tokens, "-preset")
            crf_raw = _flag_value(tokens, "-crf")
            if preset:
                presets.append(preset)
            if crf_raw is not None:
                try:
                    crfs.append(int(crf_raw))
                except ValueError:
                    pass

    reencode_preset = presets[-1] if presets else None
    reencode_crf = crfs[-1] if crfs else None

    if reencode_observed:
        passed = reencode_preset == "veryfast" and reencode_crf == 21
        note = "" if passed else "bad re-encode knobs"
    else:
        passed = copy_observed
        note = "no re-encode observed" if passed else "copy not observed"

    return HotPathVerdict(
        copy_observed=copy_observed,
        reencode_observed=reencode_observed,
        reencode_preset=reencode_preset,
        reencode_crf=reencode_crf,
        argv_recovered=True,
        passed=passed,
        note=note,
    )


def _load_text(argv: Sequence[str]) -> str:
    if not argv:
        return ""
    if argv[0] == "-":
        return sys.stdin.read()
    return read_evidence_file(argv[0])


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    verdict = parse_ffmpeg_evidence(_load_text(args))
    print(json.dumps(asdict(verdict), indent=2))
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
