"""
src/media/realtime_video_engine.py - Real-Time Dynamic Code-to-Video Production Engine.

Generates custom procedural HTML5/Three.js/WebGL code dynamically for any topic or
canonical SceneManifestV2, renders it frame-by-frame deterministically via headless
Chromium (Playwright), and composites it live with local audio (voice TTS + sidechain ducked
ambient music) and safe-area ASS subtitles with explicit stream mapping.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.ffmpeg import run_ffmpeg, FFmpegExecutionError
from src.core.scenic_detector import detect_scenic_loop, detect_subtitle_style
from src.log import get_logger

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
logger = get_logger("realtime_video_engine")

# Auto-detect available Chromium Headless Shell or browser binaries
DEFAULT_CHROME_CANDIDATES = [
    os.environ.get("PLAYWRIGHT_CHROME_EXECUTABLE_PATH", ""),
    "/opt/hermes/playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell",
    "/opt/hermes/playwright/chromium-1228/chrome-linux/chrome",
    "/opt/hermes/playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell",
    "/opt/hermes/playwright/chromium-1234/chrome-linux/chrome",
    shutil.which("google-chrome") or "",
    shutil.which("chromium-browser") or "",
    shutil.which("chromium") or "",
]


def resolve_chrome_executable() -> Optional[str]:
    """Finds the first valid and executable Chrome/Chromium binary path."""
    for candidate in DEFAULT_CHROME_CANDIDATES:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


CHROME_EXEC_PATH = resolve_chrome_executable()


@dataclass
class TemporalAct:
    """Represents a discrete temporal narrative act within the global timeline."""
    act_index: int
    start_sec: float
    duration_sec: float
    end_sec: float
    label: str
    title: str
    badge: str
    telemetry_line1: str
    telemetry_line2: str
    theme_color: str
    environment: str  # 'bunker', 'cloners', 'neural', 'vortex', 'terminal'
    camera_motion: str  # 'dolly_in', 'lateral_track', 'orbital_ascend', 'vortex_tilt', 'tactical_pan'
    excerpt: Optional[str] = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_default_temporal_acts(
    topic: str,
    total_duration_sec: float = 10.0,
    scenic_loop: str = "scp_facility",
) -> List[TemporalAct]:
    """Builds a 5-act structured temporal manifest when none is provided."""
    duration_per_act = max(1.0, total_duration_sec / 5.0)
    
    act_configs = [
        {
            "label": "ACTO I: EXPEDIENTE CLASIFICADO",
            "title": "LA CIUDADELA SUBTERRÁNEA",
            "badge": "NIVEL 5 // ACCESO O5",
            "t1": "TELEMETRÍA: PROFUNDIDAD 1.8 KM // SENSOR SÍSMICO ACTIVO",
            "t2": "COMPLEJO DE TUNGSTENO // BARRERA TELEKILL ONLINE",
            "color": "#00FF88",
            "env": "bunker",
            "motion": "dolly_in",
        },
        {
            "label": "ACTO II: LA MÁQUINA DE DIOS",
            "title": "INCUBADORAS CRIOGÉNICAS BZHR",
            "badge": "CLASE: THAUMIEL // MÁXIMO SECRETO",
            "t1": "MATRIZ BIOLÓGICA: SÍNTESIS DE ADN HOMINIS EN CURSO",
            "t2": "500,000 UNIDADES REPLICADORAS // FLUJO DE GEL 100%",
            "color": "#00E5FF",
            "env": "cloners",
            "motion": "lateral_track",
        },
        {
            "label": "ACTO III: LA GRAN FALSIFICACIÓN",
            "title": "ARCHIVO NEMOTÉCNICO ENNUI",
            "badge": "ALERTA // ANOMALÍA COGNITIVA",
            "t1": "RED NEURONAL ANÓMALA: IMPLANTACIÓN DE MEMORIA GLOBAL",
            "t2": "PROYECTO ENNUI-5: PROTOCOLO DE IDENTIDADES ARTIFICIALES",
            "color": "#9944FF",
            "env": "neural",
            "motion": "orbital_ascend",
        },
        {
            "label": "ACTO IV: EL COLAPSO Y LAS ANCLAS",
            "title": "EVENTO CLASE-XK & ANCLAS SCRANTON",
            "badge": "CRÍTICO // DISTORSIÓN DE REALIDAD",
            "t1": "DETECCIÓN DE CAMPO HUME: 0.12 H // PARADOJA TEMPORAL",
            "t2": "ESTABILIZADOR XACTS: CAUSALIDAD CRUZADA ANCLADA",
            "color": "#FF0033",
            "env": "vortex",
            "motion": "vortex_tilt",
        },
        {
            "label": "ACTO V: LA CRUDA VERDAD",
            "title": "TERMINAL O5 // REINICIO COMPLETADO",
            "badge": "RESOLUCIÓN // STATUS DESCONOCIDO",
            "t1": "RECONSTRUCCIÓN DEMOGRÁFICA MUNDIAL CONCLUIDA",
            "t2": "GRABACIÓN DEL ADMINISTRADOR: TIEMPO PRESTADO",
            "color": "#00FFAA",
            "env": "terminal",
            "motion": "tactical_pan",
        },
    ]

    acts: List[TemporalAct] = []
    current_time = 0.0
    for idx, cfg in enumerate(act_configs):
        dur = duration_per_act
        # Last act absorbs any remainder
        if idx == len(act_configs) - 1:
            dur = max(0.1, total_duration_sec - current_time)
        
        act = TemporalAct(
            act_index=idx + 1,
            start_sec=round(current_time, 2),
            duration_sec=round(dur, 2),
            end_sec=round(current_time + dur, 2),
            label=cfg["label"],
            title=cfg["title"],
            badge=cfg["badge"],
            telemetry_line1=cfg["t1"],
            telemetry_line2=cfg["t2"],
            theme_color=cfg["color"],
            environment=cfg["env"],
            camera_motion=cfg["motion"],
            excerpt=f"Expediente SCP // {topic}",
        )
        acts.append(act)
        current_time += dur

    return acts


def parse_manifest_to_temporal_acts(
    manifest_data: Union[Dict[str, Any], List[Dict[str, Any]], Any],
    total_duration_sec: float,
    topic: str = "SCP-2000",
) -> List[TemporalAct]:
    """Extracts or adapts a canonical SceneManifestV2 or list of acts into TemporalAct objects."""
    # Check if it's already a list of TemporalAct
    if isinstance(manifest_data, list) and manifest_data and isinstance(manifest_data[0], TemporalAct):
        return manifest_data

    # Check if it's a list of dictionaries with start/duration
    if isinstance(manifest_data, list) and manifest_data and isinstance(manifest_data[0], dict):
        acts: List[TemporalAct] = []
        env_cycle = ["bunker", "cloners", "neural", "vortex", "terminal"]
        motion_cycle = ["dolly_in", "lateral_track", "orbital_ascend", "vortex_tilt", "tactical_pan"]
        color_cycle = ["#00FF88", "#00E5FF", "#9944FF", "#FF0033", "#00FFAA"]

        for idx, item in enumerate(manifest_data):
            start = float(item.get("start_sec", item.get("start_time", 0.0)))
            dur = float(item.get("duration_sec", item.get("duration", total_duration_sec / len(manifest_data))))
            env = item.get("environment", env_cycle[idx % len(env_cycle)])
            motion = item.get("camera_motion", motion_cycle[idx % len(motion_cycle)])
            color = item.get("theme_color", item.get("color", color_cycle[idx % len(color_cycle)]))
            
            act = TemporalAct(
                act_index=idx + 1,
                start_sec=round(start, 2),
                duration_sec=round(dur, 2),
                end_sec=round(start + dur, 2),
                label=item.get("label", f"ACTO {idx+1}: EXPEDIENTE CONFIDENCIAL"),
                title=item.get("title", f"SECTOR CLASIFICADO {idx+1}"),
                badge=item.get("badge", "NIVEL 5 // ACCESO O5"),
                telemetry_line1=item.get("telemetry_line1", f"TELEMETRÍA SECTOR {idx+1}: STATUS OPERACIONAL"),
                telemetry_line2=item.get("telemetry_line2", f"CANAL SEGURO // PROTOCOLO ACTIVO"),
                theme_color=color,
                environment=env,
                camera_motion=motion,
                excerpt=item.get("excerpt", ""),
            )
            acts.append(act)
        return acts

    # Check if it's a dictionary representing SceneManifestV2
    if isinstance(manifest_data, dict) and "scenes" in manifest_data:
        scenes = manifest_data.get("scenes", [])
        if not scenes:
            return build_default_temporal_acts(topic, total_duration_sec)

        acts: List[TemporalAct] = []
        for idx, sc in enumerate(scenes):
            start = float(sc.get("start_sec", 0.0))
            dur = float(sc.get("duration_sec", total_duration_sec / len(scenes)))
            env_name = sc.get("environment_name", f"Sector {idx+1}")
            tension = int(sc.get("tension_level", 3))
            
            # Map tension/name to environment
            if tension >= 5 or "vortex" in env_name.lower() or "xk" in env_name.lower():
                env = "vortex"
                motion = "vortex_tilt"
                color = "#FF0033"
            elif "clon" in env_name.lower() or "bzhr" in env_name.lower() or "dna" in env_name.lower():
                env = "cloners"
                motion = "lateral_track"
                color = "#00E5FF"
            elif "neural" in env_name.lower() or "memory" in env_name.lower() or "ennui" in env_name.lower() or "brain" in env_name.lower():
                env = "neural"
                motion = "orbital_ascend"
                color = "#9944FF"
            elif "terminal" in env_name.lower() or "o5" in env_name.lower() or "control" in env_name.lower() or tension == 1:
                env = "terminal"
                motion = "tactical_pan"
                color = "#00FFAA"
            else:
                env = "bunker"
                motion = "dolly_in"
                color = "#00FF88"

            act = TemporalAct(
                act_index=idx + 1,
                start_sec=round(start, 2),
                duration_sec=round(dur, 2),
                end_sec=round(start + dur, 2),
                label=f"ESCENA {idx+1}: {env_name.upper()}",
                title=env_name.upper(),
                badge=f"TENSIÓN: NIVEL {tension} // CLASIFICADO",
                telemetry_line1=f"TELEMETRÍA: SENSOR HUME ACTIVO // SECTOR {idx+1}",
                telemetry_line2=f"SISTEMA EN LÍNEA // FORMATO T-{int(start//60):02d}:{int(start%60):02d}",
                theme_color=color,
                environment=env,
                camera_motion=motion,
                excerpt=sc.get("prompt_used", ""),
            )
            acts.append(act)
        return acts

    # Default fallback
    return build_default_temporal_acts(topic, total_duration_sec)


def generate_realtime_html_code(
    topic: str,
    manifest: Optional[Union[Dict[str, Any], List[Dict[str, Any]], List[TemporalAct], Any]] = None,
    scenic_loop: str = "scp_facility",
    width: int = 1920,
    height: int = 1080,
    duration_sec: float = 10.0,
    fps: int = 30,
) -> str:
    """
    Synthesizes custom self-contained procedural Three.js multiscene cinematic code
    with 5 distinct PBR/Shader environments, tactical CRT HUD, audio spectrum visualizer,
    and exact frame-by-frame narrative synchronization from the temporal manifest.
    """
    total_frames = max(1, int(round(duration_sec * fps)))
    
    # Resolve temporal acts
    if manifest:
        acts = parse_manifest_to_temporal_acts(manifest, duration_sec, topic)
    else:
        acts = build_default_temporal_acts(topic, duration_sec, scenic_loop)

    acts_json = json.dumps([a.to_dict() for a in acts], ensure_ascii=False)
    
    # Safe area margin calculation (16:9 vs 9:16)
    is_vertical = height > width
    hud_padding = "35px 25px" if is_vertical else "40px 50px"
    title_font_size = "18px" if is_vertical else "22px"
    act_title_font_size = "20px" if is_vertical else "26px"
    
    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SCP Classified Document - {topic}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; }}
    body {{
      background: #02050A;
      width: {width}px;
      height: {height}px;
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: 'Courier New', 'Consolas', monospace;
      color: #00FF88;
      position: relative;
    }}
    #c {{
      width: {width}px;
      height: {height}px;
      display: block;
      position: absolute;
      top: 0; left: 0;
      z-index: 1;
    }}
    /* CRT Scanlines, Vignette and Chromatic Aberration overlay */
    #crt-overlay {{
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.45) 50%),
                  radial-gradient(circle at center, transparent 40%, rgba(0, 0, 0, 0.9) 100%);
      background-size: 100% 4px, 100% 100%;
      pointer-events: none;
      z-index: 10;
      transition: filter 0.2s ease;
    }}
    /* Tactical Military HUD */
    #hud-layer {{
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      padding: {hud_padding};
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      pointer-events: none;
      z-index: 20;
      text-shadow: 0 0 10px rgba(0, 255, 136, 0.7);
    }}
    .hud-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid rgba(0, 255, 136, 0.3);
      padding-bottom: 12px;
    }}
    .hud-title {{
      font-size: {title_font_size};
      font-weight: 900;
      letter-spacing: 3px;
    }}
    .hud-badge {{
      background: rgba(255, 0, 51, 0.2);
      border: 1px solid #FF0033;
      color: #FF3366;
      padding: 5px 12px;
      font-size: 13px;
      letter-spacing: 2px;
      text-shadow: 0 0 8px #FF0033;
      border-radius: 3px;
      white-space: nowrap;
    }}
    .hud-act-center {{
      align-self: center;
      text-align: center;
      background: rgba(2, 5, 10, 0.75);
      border: 1px solid rgba(0, 255, 136, 0.4);
      padding: 10px 24px;
      border-radius: 4px;
      box-shadow: 0 0 25px rgba(0, 0, 0, 0.9);
      max-width: 85%;
    }}
    .hud-act-label {{
      font-size: 12px;
      letter-spacing: 3px;
      color: #00E5FF;
      margin-bottom: 3px;
    }}
    .hud-act-title {{
      font-size: {act_title_font_size};
      font-weight: 900;
      letter-spacing: 2px;
      color: #FFFFFF;
      text-shadow: 0 0 12px rgba(0, 255, 136, 0.8);
    }}
    .hud-footer {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      border-top: 1px solid rgba(0, 255, 136, 0.2);
      padding-top: 12px;
      font-size: 12px;
      letter-spacing: 2px;
    }}
    /* Animated audio spectrum visualizer */
    .spectrum-container {{
      display: flex;
      gap: 3px;
      align-items: flex-end;
      height: 32px;
    }}
    .spectrum-bar {{
      width: 4px;
      background: #00FF88;
      box-shadow: 0 0 6px #00FF88;
      border-radius: 1px;
    }}
    .radar-box {{
      width: 55px;
      height: 55px;
      border: 1px solid #00FF88;
      border-radius: 50%;
      position: relative;
      overflow: hidden;
      box-shadow: 0 0 10px rgba(0, 255, 136, 0.3);
      flex-shrink: 0;
    }}
    .radar-sweep {{
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      background: conic-gradient(from 0deg, rgba(0, 255, 136, 0.45), transparent 60deg);
      border-radius: 50%;
    }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
</head>
<body>
  <div id="crt-overlay"></div>
  
  <div id="hud-layer">
    <div class="hud-header">
      <div>
        <div class="hud-title">⚡ FUNDACIÓN SCP // ARCHIVO CLASIFICADO</div>
        <div id="protocolSub" style="font-size: 11px; color: #88FFAA; margin-top: 3px;">SEC_PROTOCOL: LÁZARO-2000-XK // AUTORIZACIÓN O5</div>
      </div>
      <div style="display: flex; gap: 15px; align-items: center;">
        <div class="radar-box"><div class="radar-sweep" id="radarSweep"></div></div>
        <div class="hud-badge" id="hudBadge">NIVEL 5 // RESTRINGIDO</div>
      </div>
    </div>

    <div class="hud-act-center" id="actCenter">
      <div class="hud-act-label" id="actLabel">ACTO I: REGISTRO CLASIFICADO</div>
      <div class="hud-act-title" id="actTitle">LA CALDERA DE YELLOWSTONE</div>
    </div>

    <div class="hud-footer">
      <div>
        <div id="telemetryLine1">TELEMETRÍA: PROFUNDIDAD 1.8 KM // SENSOR RAD: ESTABLE</div>
        <div id="telemetryLine2" style="color: #66CC99; font-size: 11px; margin-top: 3px;">SISTEMA BZHR: ONLINE // REGISTRO TEMPORAL T-00:00</div>
      </div>
      <div class="spectrum-container" id="spectrum">
        <!-- 16 Spectrum Bars -->
        <div class="spectrum-bar" style="height: 10px;"></div>
        <div class="spectrum-bar" style="height: 18px;"></div>
        <div class="spectrum-bar" style="height: 25px;"></div>
        <div class="spectrum-bar" style="height: 30px;"></div>
        <div class="spectrum-bar" style="height: 20px;"></div>
        <div class="spectrum-bar" style="height: 14px;"></div>
        <div class="spectrum-bar" style="height: 28px;"></div>
        <div class="spectrum-bar" style="height: 32px;"></div>
        <div class="spectrum-bar" style="height: 22px;"></div>
        <div class="spectrum-bar" style="height: 16px;"></div>
        <div class="spectrum-bar" style="height: 29px;"></div>
        <div class="spectrum-bar" style="height: 24px;"></div>
        <div class="spectrum-bar" style="height: 19px;"></div>
        <div class="spectrum-bar" style="height: 12px;"></div>
        <div class="spectrum-bar" style="height: 22px;"></div>
        <div class="spectrum-bar" style="height: 15px;"></div>
      </div>
    </div>
  </div>

  <canvas id="c" width="{width}" height="{height}"></canvas>

  <script>
    const width = {width};
    const height = {height};
    const canvas = document.getElementById('c');
    const totalDurationSec = {duration_sec};
    const acts = {acts_json};
    
    // Procedural Texture Synthesizer (Hazard warning stripes & grid patterns)
    function createHazardTexture() {{
      const cvs = document.createElement('canvas');
      cvs.width = 128;
      cvs.height = 128;
      const ctx = cvs.getContext('2d');
      ctx.fillStyle = '#111';
      ctx.fillRect(0, 0, 128, 128);
      ctx.fillStyle = '#FF9900';
      for (let i = -128; i < 256; i += 32) {{
        ctx.beginPath();
        ctx.moveTo(i, 0);
        ctx.lineTo(i + 32, 0);
        ctx.lineTo(i - 32, 128);
        ctx.lineTo(i - 64, 128);
        ctx.closePath();
        ctx.fill();
      }}
      const tex = new THREE.CanvasTexture(cvs);
      tex.wrapS = THREE.RepeatWrapping;
      tex.wrapT = THREE.RepeatWrapping;
      return tex;
    }}
    const hazardTex = createHazardTexture();
    hazardTex.repeat.set(4, 1);

    // Three.js Scene Setup
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x02050A, 0.035);
    
    const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 1000);
    camera.position.set(0, 0, 10);
    
    const renderer = new THREE.WebGLRenderer({{
      canvas: canvas,
      antialias: true,
      preserveDrawingBuffer: true,
      alpha: false
    }});
    renderer.setSize(width, height, false);
    renderer.setPixelRatio(1.0);
    renderer.setClearColor(0x02050A, 1.0);
    
    // Lighting setup
    const ambientLight = new THREE.AmbientLight(0x0a1520, 2.0);
    scene.add(ambientLight);
    
    const keyLight = new THREE.DirectionalLight(0x00FF88, 3.2);
    keyLight.position.set(8, 12, 10);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0xFF0033, 2.5);
    rimLight.position.set(-8, -10, -6);
    scene.add(rimLight);

    const pointLight = new THREE.PointLight(0x00E5FF, 3.0, 30);
    pointLight.position.set(0, 0, 2);
    scene.add(pointLight);

    // =========================================================================
    // 3D ENVIRONMENT 1: COMPLEJO DE CONTENCIÓN / BÚNKER SUBTERRÁNEO
    // =========================================================================
    const bunkerGroup = new THREE.Group();
    
    // Tunnel Modular Archways
    const archCount = 9;
    for (let i = 0; i < archCount; i++) {{
      const zPos = (i - archCount / 2) * 3.5;
      const archGeom = new THREE.BoxGeometry(7.0, 5.0, 0.4);
      const archMat = new THREE.MeshStandardMaterial({{
        color: 0x223344,
        roughness: 0.7,
        metalness: 0.6,
        wireframe: false,
      }});
      const archMesh = new THREE.Mesh(archGeom, archMat);
      archMesh.position.set(0, 0, zPos);
      
      const pillarL = new THREE.Mesh(new THREE.BoxGeometry(0.6, 4.5, 0.5), new THREE.MeshStandardMaterial({{ color: 0x112233, roughness: 0.8, metalness: 0.5 }}));
      pillarL.position.set(-2.8, 0, zPos);
      const pillarR = pillarL.clone();
      pillarR.position.set(2.8, 0, zPos);
      
      bunkerGroup.add(pillarL);
      bunkerGroup.add(pillarR);
    }}

    // Central Tungsten Vault Core (Torus Knot with PBR Material)
    const vaultGeom = new THREE.TorusKnotGeometry(2.0, 0.55, 128, 32);
    const vaultMat = new THREE.MeshStandardMaterial({{
      color: 0x00FF88,
      roughness: 0.25,
      metalness: 0.9,
      wireframe: true,
      emissive: 0x002211,
      emissiveIntensity: 0.5
    }});
    const vaultMesh = new THREE.Mesh(vaultGeom, vaultMat);
    bunkerGroup.add(vaultMesh);

    // Rotating Emergency Hazard Beacon
    const beaconGeom = new THREE.CylinderGeometry(0.3, 0.3, 0.6, 16);
    const beaconMat = new THREE.MeshBasicMaterial({{ color: 0xFF9900 }});
    const beaconMesh = new THREE.Mesh(beaconGeom, beaconMat);
    beaconMesh.position.set(0, 2.4, 0);
    bunkerGroup.add(beaconMesh);

    scene.add(bunkerGroup);

    // =========================================================================
    // 3D ENVIRONMENT 2: INCUBADORAS CRIOGÉNICAS BZHR
    // =========================================================================
    const clonersGroup = new THREE.Group();
    
    const vatCount = 5;
    const vats = [];
    const dnaHelixes = [];
    for (let v = 0; v < vatCount; v++) {{
      const xPos = (v - (vatCount - 1) / 2) * 2.6;
      
      // Glass Outer Vat
      const vatCylGeom = new THREE.CylinderGeometry(0.9, 0.9, 4.0, 24, 1, true);
      const vatGlassMat = new THREE.MeshStandardMaterial({{
        color: 0x00E5FF,
        roughness: 0.1,
        metalness: 0.1,
        transparent: true,
        opacity: 0.45,
        wireframe: false,
      }});
      const vatMesh = new THREE.Mesh(vatCylGeom, vatGlassMat);
      vatMesh.position.set(xPos, 0, 0);
      clonersGroup.add(vatMesh);

      // Inner Luminous Core
      const coreVatGeom = new THREE.CylinderGeometry(0.4, 0.4, 3.6, 16);
      const coreVatMat = new THREE.MeshBasicMaterial({{
        color: (v % 2 === 0) ? 0x00FFAA : 0x0088FF,
        wireframe: true,
      }});
      const coreVatMesh = new THREE.Mesh(coreVatGeom, coreVatMat);
      coreVatMesh.position.set(xPos, 0, 0);
      clonersGroup.add(coreVatMesh);
      vats.push(coreVatMesh);

      // DNA Helix Strand inside central vat
      if (v === 2) {{
        const helixRings = 14;
        const dnaGroup = new THREE.Group();
        for (let r = 0; r < helixRings; r++) {{
          const ringG = new THREE.TorusGeometry(0.45, 0.04, 8, 24);
          const ringM = new THREE.MeshBasicMaterial({{ color: (r % 2 === 0) ? 0x00FF88 : 0xFF0077 }});
          const ringMesh = new THREE.Mesh(ringG, ringM);
          ringMesh.position.y = (r - helixRings / 2) * 0.25;
          ringMesh.rotation.x = Math.PI / 2;
          dnaGroup.add(ringMesh);
        }}
        dnaGroup.position.set(xPos, 0, 0);
        clonersGroup.add(dnaGroup);
        dnaHelixes.push(dnaGroup);
      }}
    }}
    scene.add(clonersGroup);

    // =========================================================================
    // 3D ENVIRONMENT 3: ARCHIVO NEMOTÉCNICO / RED NEURONAL ENNUI
    // =========================================================================
    const neuralGroup = new THREE.Group();
    
    // Neural Nodes Matrix
    const nodeCount = 35;
    const nodeGeom = new THREE.SphereGeometry(0.18, 16, 16);
    const nodeMat = new THREE.MeshBasicMaterial({{ color: 0x9944FF }});
    const nodes = [];
    const nodePositions = [];
    for (let n = 0; n < nodeCount; n++) {{
      const pos = new THREE.Vector3(
        (Math.random() - 0.5) * 8.0,
        (Math.random() - 0.5) * 6.0,
        (Math.random() - 0.5) * 6.0
      );
      nodePositions.push(pos);
      const nodeMesh = new THREE.Mesh(nodeGeom, nodeMat.clone());
      nodeMesh.position.copy(pos);
      neuralGroup.add(nodeMesh);
      nodes.push(nodeMesh);
    }}

    // Synaptic Connections (Splines)
    const lineMat = new THREE.LineBasicMaterial({{ color: 0x442288, transparent: true, opacity: 0.6 }});
    for (let i = 0; i < nodeCount; i++) {{
      for (let j = i + 1; j < nodeCount; j++) {{
        if (nodePositions[i].distanceTo(nodePositions[j]) < 3.2) {{
          const lineGeom = new THREE.BufferGeometry().setFromPoints([nodePositions[i], nodePositions[j]]);
          const line = new THREE.Line(lineGeom, lineMat);
          neuralGroup.add(line);
        }}
      }}
    }}

    // Pulsing Synaptic Memory Core Sphere
    const neuralCoreGeom = new THREE.IcosahedronGeometry(1.6, 2);
    const neuralCoreMat = new THREE.MeshStandardMaterial({{
      color: 0xAA00FF,
      wireframe: true,
      roughness: 0.1,
      metalness: 0.9,
      emissive: 0x440088,
      emissiveIntensity: 0.7
    }});
    const neuralCoreMesh = new THREE.Mesh(neuralCoreGeom, neuralCoreMat);
    neuralGroup.add(neuralCoreMesh);

    scene.add(neuralGroup);

    // =========================================================================
    // 3D ENVIRONMENT 4: VÓRTICE XK & ANCLAS DE REALIDAD SCRANTON
    // =========================================================================
    const vortexGroup = new THREE.Group();
    
    // Spacetime Singularity Icosahedron
    const singGeom = new THREE.IcosahedronGeometry(2.8, 3);
    const singMat = new THREE.MeshStandardMaterial({{
      color: 0xFF0033,
      wireframe: true,
      roughness: 0.05,
      metalness: 0.95,
      emissive: 0x880011,
      emissiveIntensity: 0.85
    }});
    const singularityMesh = new THREE.Mesh(singGeom, singMat);
    vortexGroup.add(singularityMesh);

    // Accretion Distortion Ring
    const accGeom = new THREE.RingGeometry(3.2, 4.6, 48);
    const accMat = new THREE.MeshBasicMaterial({{
      color: 0xFF3300,
      side: THREE.DoubleSide,
      wireframe: true,
    }});
    const accRing = new THREE.Mesh(accGeom, accMat);
    accRing.rotation.x = Math.PI / 2.3;
    vortexGroup.add(accRing);

    // 4 Scranton Reality Anchor Containment Pylons
    for (let a = 0; a < 4; a++) {{
      const angle = (a / 4) * Math.PI * 2;
      const pylonGeom = new THREE.BoxGeometry(0.4, 4.0, 0.4);
      const pylonMat = new THREE.MeshStandardMaterial({{ color: 0x00E5FF, emissive: 0x004488, emissiveIntensity: 0.6 }});
      const pylonMesh = new THREE.Mesh(pylonGeom, pylonMat);
      pylonMesh.position.set(Math.cos(angle) * 4.2, 0, Math.sin(angle) * 4.2);
      vortexGroup.add(pylonMesh);
    }}
    scene.add(vortexGroup);

    // =========================================================================
    // 3D ENVIRONMENT 5: CONSOLA TÁCTICA O5 / COMMAND DECK
    // =========================================================================
    const terminalGroup = new THREE.Group();
    
    // Vector Plane Grids (Floor & Ceiling Grid)
    const gridHelper = new THREE.GridHelper(16, 16, 0x00FF88, 0x004422);
    gridHelper.position.y = -2.5;
    terminalGroup.add(gridHelper);

    // Holographic Hexagonal Status Cylinder
    const hexGeom = new THREE.CylinderGeometry(2.4, 2.4, 3.2, 6, 1, true);
    const hexMat = new THREE.MeshBasicMaterial({{
      color: 0x00FFAA,
      wireframe: true,
      transparent: true,
      opacity: 0.65
    }});
    const hexMesh = new THREE.Mesh(hexGeom, hexMat);
    terminalGroup.add(hexMesh);

    // Rotating Tactical Crosshair Spheres
    const crossGeom = new THREE.RingGeometry(1.2, 1.3, 32);
    const crossMat = new THREE.MeshBasicMaterial({{ color: 0x00E5FF, side: THREE.DoubleSide }});
    const crossMesh = new THREE.Mesh(crossGeom, crossMat);
    terminalGroup.add(crossMesh);

    scene.add(terminalGroup);

    // =========================================================================
    // AMBIENT PARTICULATE NEBULA
    // =========================================================================
    const pCount = 900;
    const pGeom = new THREE.BufferGeometry();
    const pPos = new Float32Array(pCount * 3);
    for (let i = 0; i < pCount * 3; i += 3) {{
      pPos[i] = (Math.random() - 0.5) * 40;
      pPos[i+1] = (Math.random() - 0.5) * 40;
      pPos[i+2] = (Math.random() - 0.5) * 40;
    }}
    pGeom.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    const pMat = new THREE.PointsMaterial({{
      color: 0x00FFAA,
      size: 0.12,
      transparent: true,
      opacity: 0.75
    }});
    const particles = new THREE.Points(pGeom, pMat);
    scene.add(particles);

    // DOM Elements for HUD
    const crtOverlay = document.getElementById('crt-overlay');
    const actLabelElem = document.getElementById('actLabel');
    const actTitleElem = document.getElementById('actTitle');
    const hudBadgeElem = document.getElementById('hudBadge');
    const t1Elem = document.getElementById('telemetryLine1');
    const t2Elem = document.getElementById('telemetryLine2');
    const radarElem = document.getElementById('radarSweep');
    const spectrumBars = document.querySelectorAll('.spectrum-bar');
    const protocolSubElem = document.getElementById('protocolSub');

    // Helper: Find current Act by time offset
    function findActByTime(tSec) {{
      for (let i = 0; i < acts.length; i++) {{
        if (tSec >= acts[i].start_sec && tSec < acts[i].end_sec) {{
          return {{ act: acts[i], index: i }};
        }}
      }}
      return {{ act: acts[acts.length - 1], index: acts.length - 1 }};
    }}

    // Deterministic Time-stepped render function for Playwright
    window.renderFrame = function(frameIndex, totalFrames) {{
      const progress = frameIndex / Math.max(1, totalFrames);
      const currentTimeSec = progress * totalDurationSec;
      const {{ act: currentAct, index: actIdx }} = findActByTime(currentTimeSec);
      
      const localActProgress = (currentTimeSec - currentAct.start_sec) / Math.max(0.01, currentAct.duration_sec);
      const globalAngle = progress * Math.PI * 2;
      const localAngle = localActProgress * Math.PI * 2;

      // Update HUD elements
      actLabelElem.textContent = currentAct.label;
      actTitleElem.textContent = currentAct.title;
      hudBadgeElem.textContent = currentAct.badge;
      t1Elem.textContent = currentAct.telemetry_line1;
      t2Elem.textContent = `${{currentAct.telemetry_line2}} // T-${{Math.floor(currentTimeSec / 60)}}:${{('0' + Math.floor(currentTimeSec % 60)).slice(-2)}}`;
      radarElem.style.transform = `rotate(${{frameIndex * 14}}deg)`;

      // Reactive chromatic aberration glitch spike on act transitions
      if (localActProgress < 0.08) {{
        crtOverlay.style.filter = `drop-shadow(3px 0px 0px rgba(255, 0, 51, 0.8)) drop-shadow(-3px 0px 0px rgba(0, 229, 255, 0.8))`;
      }} else {{
        crtOverlay.style.filter = 'none';
      }}

      // Animate Audio Spectrum Bars
      spectrumBars.forEach((bar, idx) => {{
        const h = 6 + Math.abs(Math.sin(globalAngle * 8 + idx * 0.55)) * 24;
        bar.style.height = `${{h}}px`;
        bar.style.background = currentAct.theme_color;
      }});

      // Environment visibility & procedural animation
      const env = currentAct.environment;
      bunkerGroup.visible = (env === 'bunker');
      clonersGroup.visible = (env === 'cloners');
      neuralGroup.visible = (env === 'neural');
      vortexGroup.visible = (env === 'vortex');
      terminalGroup.visible = (env === 'terminal');

      if (env === 'bunker') {{
        vaultMesh.rotation.x = globalAngle * 2.5;
        vaultMesh.rotation.y = globalAngle * 3.0;
        beaconMesh.rotation.y = globalAngle * 8.0;
      }} else if (env === 'cloners') {{
        vats.forEach((vat, idx) => {{
          vat.scale.y = 1.0 + Math.sin(localAngle * 2 + idx) * 0.15;
        }});
        dnaHelixes.forEach(dna => {{
          dna.rotation.y = localAngle * 3.0;
        }});
      }} else if (env === 'neural') {{
        neuralCoreMesh.rotation.x = localAngle * 2.0;
        neuralCoreMesh.rotation.y = localAngle * 2.5;
        nodes.forEach((node, idx) => {{
          const pulse = 1.0 + Math.sin(localAngle * 4 + idx * 0.7) * 0.35;
          node.scale.setScalar(pulse);
        }});
      }} else if (env === 'vortex') {{
        singularityMesh.rotation.x = -localAngle * 4.0;
        singularityMesh.rotation.y = localAngle * 5.0;
        singularityMesh.scale.setScalar(1.0 + Math.cos(localAngle * 6) * 0.25);
        accRing.rotation.z = localAngle * 4.5;
      }} else if (env === 'terminal') {{
        hexMesh.rotation.y = localAngle * 2.0;
        crossMesh.rotation.z = -localAngle * 3.0;
      }}

      // Cinematic Camera Choreography based on camera_motion
      const motion = currentAct.camera_motion;
      if (motion === 'dolly_in') {{
        camera.position.set(0, 0.5, 11.0 - localActProgress * 4.5);
        camera.lookAt(0, 0, 0);
      }} else if (motion === 'lateral_track') {{
        camera.position.set((localActProgress - 0.5) * 6.0, 0.4, 7.5);
        camera.lookAt((localActProgress - 0.5) * 2.0, 0, 0);
      }} else if (motion === 'orbital_ascend') {{
        const orbAngle = localActProgress * Math.PI * 1.5;
        camera.position.set(Math.sin(orbAngle) * 7.5, (localActProgress - 0.5) * 4.0, Math.cos(orbAngle) * 7.5);
        camera.lookAt(0, 0, 0);
      }} else if (motion === 'vortex_tilt') {{
        const shake = (Math.random() - 0.5) * 0.12;
        camera.position.set(Math.sin(localAngle) * 6.5 + shake, Math.cos(localAngle * 0.5) * 2.5, 7.0);
        camera.rotation.z = Math.sin(localAngle * 2) * 0.15;
        camera.lookAt(0, 0, 0);
      }} else {{
        // tactical_pan
        camera.position.set(Math.sin(localAngle * 0.8) * 8.0, 3.5, Math.cos(localAngle * 0.8) * 8.0);
        camera.lookAt(0, -0.5, 0);
      }}

      // Dynamic light color based on active Act theme
      pointLight.color.set(currentAct.theme_color);
      particles.rotation.y = globalAngle * 0.5;

      renderer.render(scene, camera);
    }};

    // Initial render call
    window.renderFrame(0, {total_frames});
  </script>
</body>
</html>
"""
    return html_content


class RealtimeVideoEngine:
    """Orchestrates dynamic procedural code writing, headless rendering, and local audio mastering."""

    def __init__(self, work_dir: Optional[Path] = None) -> None:
        self.work_dir = work_dir or (ROOT_DIR / "work" / "realtime")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.chrome_exec = CHROME_EXEC_PATH if (CHROME_EXEC_PATH and Path(CHROME_EXEC_PATH).is_file()) else None

    def render_procedural_video(
        self,
        topic: str,
        output_mp4: Path,
        manifest: Optional[Union[Dict[str, Any], List[Dict[str, Any]], List[TemporalAct], Any]] = None,
        scenic_loop: Optional[str] = None,
        width: int = 1920,
        height: int = 1080,
        duration_sec: float = 10.0,
        fps: int = 30,
        audio_path: Optional[Path] = None,
        subtitles_ass_path: Optional[Path] = None,
        clean_temp: bool = True,
    ) -> Path:
        """
        Synthesizes procedural HTML code with exact temporal sync, renders via Playwright, and encodes with FFmpeg.
        """
        from playwright.sync_api import sync_playwright

        run_id = f"realtime_{int(time.time())}_{os.getpid()}"
        run_folder = self.work_dir / run_id
        run_folder.mkdir(parents=True, exist_ok=True)

        scenic = scenic_loop or detect_scenic_loop(topic)
        total_frames = max(1, int(round(duration_sec * fps)))

        logger.info("=======================================================")
        logger.info("🎨 Real-Time Multiscene Procedural Engine")
        logger.info("Tema: '%s' | Formato: %dx%d @ %dfps (%.2fs, %d frames)", topic, width, height, fps, duration_sec, total_frames)
        logger.info("Directorio temporal: %s", run_folder)
        logger.info("=======================================================")

        # Step 1: Generate dynamic multiscene procedural code with temporal manifest
        code_html = generate_realtime_html_code(
            topic=topic,
            manifest=manifest,
            scenic_loop=scenic,
            width=width,
            height=height,
            duration_sec=duration_sec,
            fps=fps,
        )
        html_file = run_folder / "generated_scene.html"
        html_file.write_text(code_html, encoding="utf-8")
        logger.info("Código Three.js/WebGL procedural sintetizado: %s (%d bytes)", html_file.name, len(code_html))

        # Step 2: Prepare FFmpeg pipe for pure video (NO audio stream in raw video)
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        raw_video_mp4 = run_folder / "raw_procedural_stream.mp4"

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-v", "error",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-r", str(fps),
            "-i", "-",
            "-an",  # Explicitly NO audio stream in raw render
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            "-preset", "veryfast",
            "-movflags", "+faststart",
            str(raw_video_mp4),
        ]

        logger.info("Renderizando %d cuadros headless con Playwright y Chromium...", total_frames)
        start_render_t = time.time()

        launch_kwargs: Dict[str, Any] = {
            "headless": True,
            "args": [
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--hide-scrollbars",
            ],
        }
        if self.chrome_exec:
            launch_kwargs["executable_path"] = self.chrome_exec

        proc = None
        stderr_log = self.work_dir / f"ffmpeg_render_{time.time_ns()}.log"
        stderr_f = open(stderr_log, "wb+")
        try:
            proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stderr=stderr_f,
                start_new_session=True,
            )
            with sync_playwright() as p:
                browser = p.chromium.launch(**launch_kwargs)
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"file://{html_file.resolve()}")
                canvas_elem = page.locator("body")

                for frame_idx in range(total_frames):
                    page.evaluate(
                        "([f, total]) => { window.renderFrame(f, total); }",
                        [frame_idx, total_frames],
                    )
                    frame_bytes = canvas_elem.screenshot(type="png")
                    try:
                        proc.stdin.write(frame_bytes)
                    except BrokenPipeError:
                        break

                browser.close()

            proc.stdin.close()
            proc.wait()
            if proc.returncode != 0:
                stderr_f.seek(0)
                err_text = stderr_f.read().decode("utf-8", errors="ignore")
                raise FFmpegExecutionError(
                    f"FFmpeg render pipeline failed with returncode {proc.returncode}: {err_text}",
                    returncode=proc.returncode,
                    stderr=err_text,
                    command=ffmpeg_cmd,
                )
        except BrokenPipeError:
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
                proc.wait()
            raise FFmpegExecutionError(
                "FFmpeg render pipeline failed: Broken pipe",
                returncode=proc.returncode if proc else None,
                command=ffmpeg_cmd,
            )
        finally:
            if proc:
                if proc.stdin and not proc.stdin.closed:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    proc.wait()
            try:
                stderr_f.close()
                if stderr_log.is_file() and (proc is None or proc.returncode == 0):
                    stderr_log.unlink(missing_ok=True)
            except Exception:
                pass

        render_elapsed = time.time() - start_render_t
        logger.info("Renderizado procedural completado en %.2fs (%.1f fps efectivos)", render_elapsed, total_frames / max(0.1, render_elapsed))

        # Step 3: Composite with local audio and subtitles if provided
        if audio_path and audio_path.is_file():
            logger.info("Componiendo video procedural con la pista de audio masterizada...")
            self._composite_with_explicit_audio(
                video_input=raw_video_mp4,
                audio_input=audio_path,
                output_final=output_mp4,
                subtitles_ass_path=subtitles_ass_path,
                duration_sec=duration_sec,
            )
        else:
            shutil.copy2(raw_video_mp4, output_mp4)

        if clean_temp and run_folder.exists():
            shutil.rmtree(run_folder, ignore_errors=True)
            logger.info("Directorio temporal %s limpiado.", run_folder.name)

        logger.info("✅ Video generado en: %s (%d KB)", output_mp4, output_mp4.stat().st_size // 1024)
        return output_mp4

    def _composite_with_explicit_audio(
        self,
        video_input: Path,
        audio_input: Path,
        output_final: Path,
        subtitles_ass_path: Optional[Path] = None,
        duration_sec: float = 10.0,
    ) -> None:
        """Merges procedural video, local audio, and subtitles with strict explicit stream mapping."""
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-stream_loop", "-1", "-i", str(video_input),
            "-i", str(audio_input),
        ]

        filter_complex = []
        video_map = "0:v:0"

        # Apply ASS Subtitles if provided
        if subtitles_ass_path and subtitles_ass_path.is_file():
            sub_escaped = str(subtitles_ass_path).replace(":", "\\:").replace("'", "\\'")
            filter_complex.append(f"[{video_map}]ass='{sub_escaped}'[v_sub]")
            video_map = "v_sub"

        if filter_complex:
            cmd += ["-filter_complex", ";".join(filter_complex), "-map", f"[{video_map}]", "-map", "1:a:0"]
            cmd += [
                "-t", str(duration_sec),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-movflags", "+faststart",
                str(output_final),
            ]
        else:
            cmd += ["-map", "0:v:0", "-map", "1:a:0"]
            cmd += [
                "-t", str(duration_sec),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-movflags", "+faststart",
                str(output_final),
            ]

        run_ffmpeg(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Real-Time Procedural Code-to-Video Engine")
    parser.add_argument("--topic", type=str, required=True, help="Video topic")
    parser.add_argument("--theme", type=str, default=None, help="Scenic theme")
    parser.add_argument("--duration", type=float, default=5.0, help="Duration in seconds")
    parser.add_argument("--output", type=str, default=None, help="Output MP4 file path")
    parser.add_argument("--horizontal", action="store_true", default=False, help="Render 16:9 instead of 9:16")
    parser.add_argument("--keep-temp", action="store_true", default=False, help="Do not delete temporary code/frames")
    args = parser.parse_args()

    w, h = (1920, 1080) if args.horizontal else (1080, 1920)
    out_path = Path(args.output) if args.output else (ROOT_DIR / "output" / f"realtime_{int(time.time())}.mp4")

    engine = RealtimeVideoEngine()
    engine.render_procedural_video(
        topic=args.topic,
        output_mp4=out_path,
        scenic_loop=args.theme,
        width=w,
        height=h,
        duration_sec=args.duration,
        clean_temp=not args.keep_temp,
    )
    print(f"Master render complete: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
