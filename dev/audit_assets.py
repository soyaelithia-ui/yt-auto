#!/usr/bin/env python3
"""
dev/audit_assets.py - Visual Asset Auditor & Anti-Filler CLI Tool.

Audits candidate visual assets or asset directories against the strict anti-filler criteria:
- Rejects generic stock photography or filler imagery.
- Approves official emblems, brandmarks, or technical schematics relevant to the topic.
- Outputs structured report conforming to schemas/image_auditor.schema.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.agents.image_auditor import ImageAuditorAgent
from src.log import get_logger

logger = get_logger("dev_audit_assets")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Visual Asset Auditor & Anti-Filler CLI Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--topic", type=str, required=True, help="Video topic / entity subject")
    parser.add_argument("--candidates-json", type=str, default=None, help="JSON string or file path with candidates")
    parser.add_argument("--lane", type=str, default="moku-scp-shorts", help="Editorial channel lane")
    parser.add_argument("--use-agent", action="store_true", default=False, help="Invoke Antigravity CLI harness")
    args = parser.parse_args()

    candidates: List[Dict[str, Any]] = []

    if args.candidates_json:
        p = Path(args.candidates_json)
        if p.is_file():
            candidates = json.loads(p.read_text(encoding="utf-8"))
        else:
            candidates = json.loads(args.candidates_json)
    else:
        # Default probe candidates
        candidates = [
            {
                "id": "asset_official_1",
                "name": "SCP Foundation Insignia Oficial",
                "source_type": "official_emblem",
            },
            {
                "id": "asset_schematic_2",
                "name": "Esquema Técnico Cámara de Contención",
                "source_type": "technical_schematic",
            },
            {
                "id": "asset_filler_3",
                "name": "Persona Asombrada Mirando al Cielo (Stock Filler)",
                "source_type": "generic_filler_photo",
            },
            {
                "id": "asset_unrelated_4",
                "name": "Logotipo Restaurante de Comida Rápida",
                "source_type": "brand_logo",
            },
        ]

    auditor = ImageAuditorAgent()
    report = auditor.audit_candidates(
        topic=args.topic,
        candidates=candidates,
        channel_lane=args.lane,
        use_agent=args.use_agent,
    )

    print("=======================================================")
    print(f"🛡️ Reporte de Auditoría Visual (Anti-Filler Policy)")
    print(f"Tema: {report['topic']} | Lane: {report['channel_lane']}")
    print(f"Total Evaluados: {report['total_candidates']} | Aprobados: {report['approved_count']} | Descartados: {report['discarded_count']}")
    print("=======================================================")
    for v in report["verdicts"]:
        icon = "✅" if v["verdict"] == "APPROVED_REFERENCE" else "🚫"
        badge = f"[{v['badge_render_type']}]" if v["badge_render_type"] != "none" else ""
        print(f"{icon} {v['entity_name']} {badge}")
        print(f"   Veredicto: {v['verdict']} (Confianza: {v['confidence_score']:.2f})")
        print(f"   Motivo: {v['reasoning']}")
        print()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
