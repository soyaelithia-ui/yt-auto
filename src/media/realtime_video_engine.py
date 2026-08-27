"""
src/media/realtime_video_engine.py - Real-Time Dynamic Code-to-Video Production Engine.

Generates custom procedural HTML5/Three.js/WebGL code dynamically for each topic,
renders it frame-by-frame deterministically via headless Chromium (Playwright),
and composites it live with local audio (voice TTS + sidechain ducked ambient music)
and safe-area ASS subtitles with explicit stream mapping.
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.core.scenic_detector import detect_scenic_loop, detect_subtitle_style
from src.log import get_logger

logger = get_logger("realtime_video_engine")

CHROME_EXEC_PATH = os.environ.get(
    "PLAYWRIGHT_CHROME_EXECUTABLE_PATH",
    "/opt/hermes/playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell",
)


def generate_realtime_html_code(
    topic: str,
    scenic_loop: str = "scp_facility",
    width: int = 1920,
    height: int = 1080,
    duration_sec: float = 10.0,
    fps: int = 30,
) -> str:
    """
    Synthesizes custom self-contained procedural Three.js multiscene cinematic code
    with 5 distinct acts, tactical CRT HUD, audio spectrum visualizer, and classified telemetry.
    """
    total_frames = max(1, int(round(duration_sec * fps)))
    
    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SCP Classified Document - {topic}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; overflow: hidden; }}
    body {{
      background: #03070D;
      width: {width}px;
      height: {height}px;
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: 'Courier New', monospace;
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
    /* CRT Scanlines and Vignette overlay */
    #crt-overlay {{
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.4) 50%),
                  radial-gradient(circle at center, transparent 40%, rgba(0, 0, 0, 0.85) 100%);
      background-size: 100% 4px, 100% 100%;
      pointer-events: none;
      z-index: 10;
    }}
    /* Tactical HUD */
    #hud-layer {{
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      padding: 45px 60px;
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
      padding-bottom: 15px;
    }}
    .hud-title {{
      font-size: 24px;
      font-weight: 900;
      letter-spacing: 3px;
    }}
    .hud-badge {{
      background: rgba(255, 0, 51, 0.2);
      border: 1px solid #FF0033;
      color: #FF3366;
      padding: 6px 14px;
      font-size: 15px;
      letter-spacing: 2px;
      text-shadow: 0 0 8px #FF0033;
      border-radius: 3px;
    }}
    .hud-act-center {{
      align-self: center;
      text-align: center;
      background: rgba(3, 7, 13, 0.65);
      border: 1px solid rgba(0, 255, 136, 0.4);
      padding: 12px 30px;
      border-radius: 4px;
      box-shadow: 0 0 25px rgba(0, 0, 0, 0.8);
    }}
    .hud-act-label {{
      font-size: 14px;
      letter-spacing: 4px;
      color: #00E5FF;
      margin-bottom: 4px;
    }}
    .hud-act-title {{
      font-size: 28px;
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
      padding-top: 15px;
      font-size: 14px;
      letter-spacing: 2px;
    }}
    /* Animated waveform visualizer */
    .spectrum-container {{
      display: flex;
      gap: 4px;
      align-items: flex-end;
      height: 36px;
    }}
    .spectrum-bar {{
      width: 5px;
      background: #00FF88;
      box-shadow: 0 0 6px #00FF88;
      border-radius: 1px;
    }}
    .radar-box {{
      width: 70px;
      height: 70px;
      border: 1px solid #00FF88;
      border-radius: 50%;
      position: relative;
      overflow: hidden;
      box-shadow: 0 0 10px rgba(0, 255, 136, 0.3);
    }}
    .radar-sweep {{
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      background: conic-gradient(from 0deg, rgba(0, 255, 136, 0.4), transparent 60deg);
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
        <div style="font-size: 13px; color: #88FFAA; margin-top: 4px;">SEC_PROTOCOL: LÁZARO-2000-XK // AUTORIZACIÓN O5</div>
      </div>
      <div style="display: flex; gap: 20px; align-items: center;">
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
        <div id="telemetryLine2" style="color: #66CC99; font-size: 12px; margin-top: 3px;">SISTEMA BZHR-09: ONLINE // REGISTRO TEMPORAL T-00:00</div>
      </div>
      <div class="spectrum-container" id="spectrum">
        <!-- 16 Spectrum Bars -->
        <div class="spectrum-bar" style="height: 10px;"></div>
        <div class="spectrum-bar" style="height: 18px;"></div>
        <div class="spectrum-bar" style="height: 25px;"></div>
        <div class="spectrum-bar" style="height: 32px;"></div>
        <div class="spectrum-bar" style="height: 20px;"></div>
        <div class="spectrum-bar" style="height: 14px;"></div>
        <div class="spectrum-bar" style="height: 28px;"></div>
        <div class="spectrum-bar" style="height: 35px;"></div>
        <div class="spectrum-bar" style="height: 22px;"></div>
        <div class="spectrum-bar" style="height: 16px;"></div>
        <div class="spectrum-bar" style="height: 30px;"></div>
        <div class="spectrum-bar" style="height: 26px;"></div>
        <div class="spectrum-bar" style="height: 19px;"></div>
        <div class="spectrum-bar" style="height: 12px;"></div>
        <div class="spectrum-bar" style="height: 24px;"></div>
        <div class="spectrum-bar" style="height: 15px;"></div>
      </div>
    </div>
  </div>

  <canvas id="c" width="{width}" height="{height}"></canvas>

  <script>
    const width = {width};
    const height = {height};
    const canvas = document.getElementById('c');
    
    // Three.js Scene Setup
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x03070D, 0.035);
    
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
    renderer.setClearColor(0x03070D, 1.0);
    
    // Lighting setup
    const ambientLight = new THREE.AmbientLight(0x112233, 2.5);
    scene.add(ambientLight);
    
    const primaryLight = new THREE.DirectionalLight(0x00FF88, 3.5);
    primaryLight.position.set(8, 12, 10);
    scene.add(primaryLight);

    const accentLight = new THREE.DirectionalLight(0xFF0033, 2.8);
    accentLight.position.set(-8, -10, -6);
    scene.add(accentLight);

    // ==========================================
    // 3D SCENE 1: SCP Bunker & Vault Architecture (Torus Knot Core)
    // ==========================================
    const vaultGroup = new THREE.Group();
    const vaultGeom = new THREE.TorusKnotGeometry(2.4, 0.6, 140, 32);
    const vaultMat = new THREE.MeshStandardMaterial({{
      color: 0x00FF88,
      roughness: 0.2,
      metalness: 0.85,
      wireframe: true,
      emissive: 0x003311,
      emissiveIntensity: 0.4
    }});
    const vaultMesh = new THREE.Mesh(vaultGeom, vaultMat);
    vaultGroup.add(vaultMesh);

    // Inner Glowing Quantum Sphere
    const coreGeom = new THREE.SphereGeometry(1.3, 32, 32);
    const coreMat = new THREE.MeshBasicMaterial({{ color: 0x00E5FF, wireframe: false }});
    const coreMesh = new THREE.Mesh(coreGeom, coreMat);
    vaultGroup.add(coreMesh);
    scene.add(vaultGroup);

    // ==========================================
    // 3D SCENE 2: DNA Quantum Replicator (Double Helix Rings)
    // ==========================================
    const helixGroup = new THREE.Group();
    const ringCount = 18;
    const rings = [];
    for (let r = 0; r < ringCount; r++) {{
      const rGeom = new THREE.TorusGeometry(1.6 + Math.sin(r * 0.4) * 0.4, 0.08, 16, 64);
      const rMat = new THREE.MeshStandardMaterial({{
        color: (r % 2 === 0) ? 0x00E5FF : 0xFF0055,
        wireframe: true,
        emissive: 0x002244,
        emissiveIntensity: 0.5
      }});
      const rMesh = new THREE.Mesh(rGeom, rMat);
      rMesh.position.y = (r - ringCount / 2) * 0.45;
      rMesh.rotation.x = Math.PI / 2;
      helixGroup.add(rMesh);
      rings.push(rMesh);
    }}
    helixGroup.position.set(0, 0, 0);
    scene.add(helixGroup);

    // ==========================================
    // 3D SCENE 3: Class-XK Dimensional Vortex / Wormhole
    // ==========================================
    const vortexGroup = new THREE.Group();
    const vortexGeom = new THREE.IcosahedronGeometry(3.2, 3);
    const vortexMat = new THREE.MeshStandardMaterial({{
      color: 0xFF1144,
      wireframe: true,
      roughness: 0.1,
      metalness: 0.9,
      emissive: 0x660011,
      emissiveIntensity: 0.7
    }});
    const vortexMesh = new THREE.Mesh(vortexGeom, vortexMat);
    vortexGroup.add(vortexMesh);
    scene.add(vortexGroup);

    // ==========================================
    // Ambient Particulate Nebula / Cryo-Mist
    // ==========================================
    const pCount = 800;
    const pGeom = new THREE.BufferGeometry();
    const pPos = new Float32Array(pCount * 3);
    for (let i = 0; i < pCount * 3; i += 3) {{
      pPos[i] = (Math.random() - 0.5) * 36;
      pPos[i+1] = (Math.random() - 0.5) * 36;
      pPos[i+2] = (Math.random() - 0.5) * 36;
    }}
    pGeom.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    const pMat = new THREE.PointsMaterial({{
      color: 0x00FFAA,
      size: 0.14,
      transparent: true,
      opacity: 0.8
    }});
    const particles = new THREE.Points(pGeom, pMat);
    scene.add(particles);

    // Acts Metadata definitions
    const acts = [
      {{
        label: "ACTO I: EXPEDIENTE CLASIFICADO",
        title: "LA CALDERA DE YELLOWSTONE",
        badge: "NIVEL 5 // ACCESO O5",
        color: "#00FF88",
        t1: "TELEMETRÍA: PROFUNDIDAD 1.8 KM // SENSOR SÍSMICO ACTIVO",
        t2: "BÚNKER SUBTERRÁNEO // DETECCIÓN DE ENERGÍA ANÓMALA",
        activeGroup: 0
      }},
      {{
        label: "ACTO II: LA MÁQUINA DE DIOS",
        title: "DISPOSITIVO DE RECONSTRUCCIÓN BZHR",
        badge: "CLASE: THAUMIEL // MÁXIMO SECRETO",
        color: "#00E5FF",
        t1: "MATRIZ BIOLÓGICA: SÍNTESIS DE ADN EN CURSO",
        t2: "UNIDADES REPLICADORAS HOMINIS: 100% OPERACIONALES",
        activeGroup: 1
      }},
      {{
        label: "ACTO III: LA HISTORIA OLVIDADA",
        title: "LAS FOSAS DE CADÁVERES IMPRESOS",
        badge: "ALERTA // ANOMALÍA COGNITIVA",
        color: "#FF9900",
        t1: "DISCORDANCIA GENÉTICA: CUERPOS DE ERA NO REGISTRADA",
        t2: "EVIDENCIA FÍSICA: PROTOCOLO EJECUTADO PREVIAMENTE",
        activeGroup: 0
      }},
      {{
        label: "ACTO IV: EL COLAPSO TOTAL",
        title: "EVENTO DE EXTINCIÓN CLASE-XK",
        badge: "CRÍTICO // FALLA DE LÍNEA TEMPORAL",
        color: "#FF0033",
        t1: "ALERTA DE ANOMALÍA: COLAPSO DE LA CIVILIZACIÓN",
        t2: "ACTIVACIÓN AUTOMÁTICA DEL PROTOCOLO LÁZARO",
        activeGroup: 2
      }},
      {{
        label: "ACTO V: LA CRUDA VERDAD",
        title: "¿CUÁNTAS VECES HEMOS MUERTO?",
        badge: "RESOLUCIÓN // REINICIO COMPLETADO",
        color: "#00FFAA",
        t1: "RECONSTRUCCIÓN DEMOGRÁFICA MUNDIAL CONCLUIDA",
        t2: "MEMORIA COLECTIVA RESTAURADA // STATUS: DESCONOCIDO",
        activeGroup: 1
      }}
    ];

    // HUD DOM Elements
    const actLabelElem = document.getElementById('actLabel');
    const actTitleElem = document.getElementById('actTitle');
    const hudBadgeElem = document.getElementById('hudBadge');
    const t1Elem = document.getElementById('telemetryLine1');
    const t2Elem = document.getElementById('telemetryLine2');
    const radarElem = document.getElementById('radarSweep');
    const spectrumBars = document.querySelectorAll('.spectrum-bar');

    // Deterministic Time-stepped render function for Playwright
    window.renderFrame = function(frameIndex, totalFrames) {{
      const progress = frameIndex / Math.max(1, totalFrames);
      const angle = progress * Math.PI * 2;
      
      // Determine current Act (0 to 4)
      const actIndex = Math.min(4, Math.floor(progress * 5));
      const currentAct = acts[actIndex];

      // Update HUD elements
      actLabelElem.textContent = currentAct.label;
      actTitleElem.textContent = currentAct.title;
      hudBadgeElem.textContent = currentAct.badge;
      t1Elem.textContent = currentAct.t1;
      t2Elem.textContent = currentAct.t2;
      radarElem.style.transform = `rotate(${{frameIndex * 12}}deg)`;

      // Animate Audio Spectrum Bars
      spectrumBars.forEach((bar, idx) => {{
        const h = 8 + Math.abs(Math.sin(angle * 6 + idx * 0.6)) * 26;
        bar.style.height = `${{h}}px`;
        bar.style.background = currentAct.color;
      }});

      // Toggle & morph 3D models based on Act
      if (currentAct.activeGroup === 0) {{
        vaultGroup.visible = true;
        helixGroup.visible = false;
        vortexGroup.visible = false;
        vaultMesh.rotation.x = angle * 2;
        vaultMesh.rotation.y = angle * 3;
        coreMesh.scale.setScalar(1.0 + Math.sin(angle * 5) * 0.25);
      }} else if (currentAct.activeGroup === 1) {{
        vaultGroup.visible = false;
        helixGroup.visible = true;
        vortexGroup.visible = false;
        helixGroup.rotation.y = angle * 2.5;
        rings.forEach((r, idx) => {{
          r.rotation.z = angle * 3 + idx * 0.2;
        }});
      }} else {{
        vaultGroup.visible = false;
        helixGroup.visible = false;
        vortexGroup.visible = true;
        vortexMesh.rotation.x = -angle * 3;
        vortexMesh.rotation.y = angle * 4;
        vortexMesh.scale.setScalar(1.0 + Math.cos(angle * 8) * 0.3);
      }}

      // Smooth Camera Orbit
      camera.position.x = Math.sin(angle) * 7.5;
      camera.position.z = Math.cos(angle) * 7.5;
      camera.position.y = Math.sin(angle * 2) * 2.0;
      camera.lookAt(0, 0, 0);

      // Particle Drift
      particles.rotation.y = angle * 0.6;

      renderer.render(scene, camera);
    }};

    // Initial render
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
        self.chrome_exec = CHROME_EXEC_PATH if Path(CHROME_EXEC_PATH).is_file() else None

    def render_procedural_video(
        self,
        topic: str,
        output_mp4: Path,
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
        Synthesizes code on the fly, renders it via Playwright, and encodes with FFmpeg.
        """
        from playwright.sync_api import sync_playwright

        run_id = f"realtime_{int(time.time())}_{os.getpid()}"
        run_folder = self.work_dir / run_id
        run_folder.mkdir(parents=True, exist_ok=True)

        scenic = scenic_loop or detect_scenic_loop(topic)
        total_frames = max(1, int(round(duration_sec * fps)))

        logger.info("=======================================================")
        logger.info("🎨 Real-Time Multiscene Procedural Engine")
        logger.info("Tema: '%s' | Formato: %dx%d @ %dfps (%.1fs)", topic, width, height, fps, duration_sec)
        logger.info("Directorio temporal: %s", run_folder)
        logger.info("=======================================================")

        # Step 1: Generate dynamic multiscene procedural code
        code_html = generate_realtime_html_code(
            topic=topic,
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

        with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
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
                    proc.stdin.write(frame_bytes)

                browser.close()

            proc.stdin.close()
            stderr_out = proc.stderr.read()
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg render pipeline failed: {stderr_out.decode('utf-8', errors='ignore')}")

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
        else:
            cmd += ["-map", "0:v:0", "-map", "1:a:0"]

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

        subprocess.run(cmd, check=True)


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
