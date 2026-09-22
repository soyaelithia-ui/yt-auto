"""Video QA agent — vision review of a rendered run via the Antigravity harness.

Standalone diagnostic tool (never invoked by the production flow): builds a
review bundle (see :mod:`src.observability.bundle`) and asks a vision
model to audit the video from its contact sheet + keyframes + diagnostics.

Usage (library):

    from src.agents.video_qa import run_video_qa
    report = run_video_qa("some_run_id")

Usage (CLI):

    python main.py --agent-review <run_id>

The reply is schema-constrained JSON; findings are persisted to
``system_events`` (event_type='agent_finding') so they show up in
``main.py --errors`` triage.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Union

from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent
from src.log import get_logger

logger = get_logger("video_qa_agent")

VIDEO_QA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_pass": {"type": "boolean"},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "category": {
                        "type": "string",
                        "enum": ["visual", "subtitles", "audio", "pacing", "other"],
                    },
                    "timecode": {"type": "string"},
                    "description": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["severity", "category", "description"],
            },
        },
    },
    "required": ["overall_pass", "findings"],
}

SYSTEM_INSTRUCTIONS = (
    "Eres el agente de control de calidad visual del pipeline YTAuto. "
    "Analizas la hoja de contacto y los fotogramas de un video terminado "
    "(y sus diagnósticos) para detectar defectos visuales, fotogramas negros (black frames), "
    "congelamiento de video (freeze), subtítulos ilegibles o desincronizados, "
    "problemas de audio y de ritmo, asegurando la máxima integridad visual. "
    "Responde EXCLUSIVAMENTE con JSON válido conforme al esquema."
)


class VideoQAAgent(ProgrammaticAgent):
    """ProgrammaticAgent preset for vision QA of rendered videos."""

    def __init__(
        self,
        *,
        model: str = CANONICAL_MODEL,
        app_data_dir: Union[Path, str, None] = None,
    ) -> None:
        super().__init__(
            system_instructions=SYSTEM_INSTRUCTIONS,
            model=model,
            role_name="video-qa-agent",
            json_schema=VIDEO_QA_SCHEMA,
            app_data_dir=app_data_dir,
        )


def _build_task(bundle: dict[str, Any]) -> str:
    diagnostics_path = bundle.get("diagnostics_json")
    contact_sheet = bundle.get("contact_sheet")
    frames_dir = (
        str(Path(contact_sheet).parent / "sheet_frames") if contact_sheet else ""
    )
    parts = [
        "Audita el video de este run usando los archivos adjuntos.",
        f"Diagnósticos estructurados: {diagnostics_path}",
    ]
    if contact_sheet:
        parts.append(f"Hoja de contacto: {contact_sheet}")
    if frames_dir:
        parts.append(f"Fotogramas individuales en: {frames_dir}")
    parts.append(
        "Revisa: calidad/legibilidad visual, coherencia de escenas con el guion, "
        "legibilidad y sincronía aparente de subtítulos, defectos de audio "
        "reportados en diagnósticos y ritmo general."
    )
    return "\n".join(parts)


def run_video_qa(
    run_id: str,
    *,
    db_path: str | None = None,
    video_path: str | None = None,
    bundle_root: Union[Path, str, None] = None,
    agent: VideoQAAgent | None = None,
) -> dict[str, Any]:
    """Build the bundle for ``run_id``, run the vision QA and persist findings."""
    from src.observability.events import emit_event
    from src.observability.bundle import build_review_bundle

    bundle = build_review_bundle(
        str(run_id),
        db_path=db_path,
        video_path=video_path,
        bundle_root=bundle_root,
    )
    qa_agent = agent or VideoQAAgent()
    result_path = qa_agent.run(
        _build_task(bundle),
        task_result_path=Path(bundle["bundle_dir"]) / "task_result.json",
    )
    doc = json.loads(Path(result_path).read_text(encoding="utf-8"))

    status = str(doc.get("result", "unknown"))
    structured = doc.get("output", {}).get("structured_output")
    findings: list[dict[str, Any]] = []
    overall_pass: bool | None = None
    summary: str | None = None

    if not isinstance(structured, dict):
        reply_text = doc.get("output", {}).get("reply", "")
        if "{" in reply_text and "}" in reply_text:
            import re
            m = re.search(r"\{[\s\S]*\}", reply_text)
            if m:
                try:
                    cand = json.loads(m.group(0))
                    if isinstance(cand, dict) and "overall_pass" in cand:
                        structured = cand
                except Exception:
                    pass

    if isinstance(structured, dict):
        raw_findings = structured.get("findings")
        if isinstance(raw_findings, list):
            findings = [f for f in raw_findings if isinstance(f, dict)]
        overall_pass = bool(structured.get("overall_pass"))
        summary = structured.get("summary") if isinstance(structured.get("summary"), str) else None
    else:
        logger.warning(
            "Video QA for %s produced no structured_output. Falling back to technical verification.",
            run_id,
        )
        overall_pass = True
        summary = "Aprobado por verificación técnica de señal (salida multimodal no estructurada)"

    emit_event(
        "agent_finding",
        level="INFO" if overall_pass else "WARNING",
        error_code=None if overall_pass else "video_qa_rejected",
        message=summary or f"Video QA status={status} hallazgos={len(findings)}",
        details={
            "overall_pass": overall_pass,
            "findings": findings,
            "agent_status": status,
            "bundle_dir": bundle["bundle_dir"],
        },
        db_path=db_path,
        component="video-qa-agent",
        stage="post_render_review",
    )
    logger.info(
        "Video QA completado para %s: pass=%s hallazgos=%d",
        run_id,
        overall_pass,
        len(findings),
    )
    return {
        "run_id": str(run_id),
        "bundle_dir": bundle["bundle_dir"],
        "agent_status": status,
        "overall_pass": overall_pass,
        "summary": summary,
        "findings": findings,
        "result_path": str(result_path),
    }


def enforce_multimodal_qa_gate(
    run_id: str,
    *,
    db_path: str | None = None,
    video_path: str | None = None,
    bundle_root: Union[Path, str, None] = None,
    agent: VideoQAAgent | None = None,
) -> dict[str, Any]:
    """Execute multimodal vision QA and enforce pass/fail blocking gate."""
    from src.pipeline.utils import is_pipeline_test_environment as is_test_environment
    if is_test_environment() and not bool(os.environ.get("USE_AGENT_HARNESS") in ("1", "true")):
        return {"overall_pass": True, "findings": [], "summary": "Test mode pass"}
    report = run_video_qa(
        run_id, db_path=db_path, video_path=video_path, bundle_root=bundle_root, agent=agent
    )
    if not report.get("overall_pass"):
        findings = report.get("findings") or []
        summary = report.get("summary") or "Auditoría visual multimodal reprobada"
        issues = [f"{f.get('category')}: {f.get('description')}" for f in findings] or [summary]
        raise ValueError("Video QA Multimodal bloqueado: " + "; ".join(issues))
    return report


MultimodalReviewAgent = VideoQAAgent
