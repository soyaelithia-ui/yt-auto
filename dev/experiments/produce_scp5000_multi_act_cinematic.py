#!/usr/bin/env python3
"""
dev/produce_scp5000_multi_act_cinematic.py - Production Suite for SCP-5000:
100% Code-Based Procedural Multi-Scene Cinematic Video (10+ min) & Dynamic Subtitled Short (49s).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from src.audio_processor import sanitize_script_for_tts
from src.media.thumbnail_engine import ResilientThumbnailEngine
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.agents.qa_auditor import VisualAudioQAAuditorAgent
from src.media.multi_act_renderer import MultiActVideoRenderer, NarrativeSceneAct

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("produce_scp5000_multi_act")

OUTPUT_DIR = ROOT_DIR / "output"
WORK_DIR = ROOT_DIR / "work" / "scp5000_cinematic_production"
AUDIO_BGM = ROOT_DIR / "assets" / "music" / "horror_ambient.mp3"


SCP5000_LONG_SCRIPT = """
En los archivos clasificados del Sitio-62C de la Fundación SCP reposa un traje mecánico de contención biológica cuya superficie de aleación ligera se encuentra chamuscada por el fuego, la radiación ionizante y el impacto de armamento anómalo. Designado oficialmente bajo la clasificación SCP-5000, este arnés tecnológico fue recuperado con el cuerpo sin vida de un técnico de mantenimiento de nivel dos llamado Pietro Wilson. Sin embargo, lo verdaderamente perturbador no era la sofisticada ingeniería cuántica del traje, sino el contenido del registro de audio y telemetría almacenado en su memoria interna: una bitácora detallada y aterradora que documenta el evento más oscuro y moralmente devastador en la historia del universo conocido. El día en que la Fundación SCP, la organización fundada para proteger a la humanidad, decidió deliberadamente y de forma unánime exterminar a toda la especie humana de la faz de la Tierra.

Durante más de un siglo, la civilización sobrevivió en las sombras gracias a la labor silenciosa y metódica de la Fundación. Científicos, guardias y agentes de campo dedicaron sus vidas a mantener encerradas a las abominaciones de la oscuridad bajo un lema inquebrantable: Asegurar, Contener y Proteger. No obstante, en una línea temporal paralela, el Consejo O5 y los miembros del Comité de Ética convocaron una sesión plenaria de emergencia bajo el protocolo de contención nemotécnica más riguroso jamás activado. Los investigadores de la División de Psico-análisis habían completado con éxito la fase final del Proyecto Pneuma, una exploración cuántica profunda del inconsciente colectivo y la noosfera de la mente humana.

Lo que los neurocientíficos descubrieron en esa dimensión psíquica no fue una iluminación mística ni una verdad divina, sino la presencia de una entidad parasitaria colosal e inmortal que habita en el alma de cada ser humano desde los albores de la evolución biológica. Esta criatura cósmica no se alimenta de materia física ni de sangre; su sustento primordial es el dolor humano, el sufrimiento físico, el terror psicológico y la angustia existencial, atrapando la conciencia de las personas en un ciclo perpetuo de tormento infinito incluso después de la muerte clínica.

Tras verificar los resultados en millones de escaneos cerebrales computarizados, algo se quebró irremediablemente en la mente de los líderes de la Fundación. Los doce miembros del Comité de Ética votaron de manera unánime su propia autodisolución, y el Consejo O5 emitió una directiva de contingencia omnicida transmitida a todos los sitios de contención del planeta. Un comunicado breve, frío y despiadado: A todo el personal de la Fundación y destacamentos militares leales: las anomalías ya no serán contenidas; a partir de este instante, serán desplegadas como armas biológicas. La Fundación SCP declara formalmente la guerra contra la humanidad. No intenten resistirse. No sientan miedo. El dolor terminará pronto.

Lo que aconteció tras esa transmisión fue la pesadilla más atroz y sangrienta jamás presenciada por la civilización. La Fundación no recurrió a bombardeos nucleares tradicionales; en su lugar, abrieron sistemáticamente las celdas de las entidades más destructivas de sus bóvedas subterráneas. Liberaron a SCP-682, el reptil inmortal e indestructible, pero esta vez reforzado cibernéticamente con placas de blindaje pesado y cañones de energía dirigida para arrasar las principales capitales de Europa y Asia. Desplegaron a SCP-096, el Chico Tímido, transmitiendo fotografías de alta resolución de su rostro en cadenas satelitales globales y vallas publicitarias, desatando una cacería imparable de cientos de millones de civiles que no tuvieron oportunidad alguna de apartar la mirada.

En las redes de distribución de agua potable de América del Norte y del Sur inyectaron cepas modificadas de patógenos anómalos que transformaban los órganos internos humanos en vidrio líquido y tejido necrótico viviente. Al mismo tiempo, enjambres de miles de réplicas de SCP-173 eran lanzadas en paracaídas desde bombarderos estratégicos sobre las ciudades sumidas en el pánico, quebrando los cuellos de cualquier persona que intentara parpadear o huir en la oscuridad.

Pietro Wilson, un técnico ordinario asignado al Sitio-06 que no formaba parte del círculo de mando ni había recibido la inmunización química administrada al personal superior, presenció con horror absoluto cómo sus propios compañeros de trabajo ejecutaban a quemarropa a los científicos disidentes, al personal Clase-D y a las familias de civiles que suplicaban refugio en los accesos blindados del complejo. Al comprender que sus superiores habían perdido todo rastro de piedad humana, Pietro se colocó el traje de exploración de sigilo SCP-5000, activó el módulo de camuflaje cuántico y escapó a través de los ductos de ventilación hacia el exterior en ruinas.

El traje SCP-5000 no era solo una armadura de combate; representaba la cúspide de la ingeniería de supervivencia. Contaba con celdas de combustible regenerativas, filtros moleculares de aire y agua, soporte médico automatizado y un visor nemotécnico capaz de registrar y analizar patrones tácticos en tiempo real. Mientras avanzaba a pie por las carreteras destrozadas y los bosques cubiertos de ceniza de Norteamérica, Pietro documentó el colapso total de la Coalición Oculta Global y de las fuerzas armadas internacionales que intentaron resistir la ofensiva de la Fundación.

Presenció el asedio y la caída de la gran fortaleza subterránea de Ganzir, donde millones de refugiados intentaron resistir tras gigantescos muros de hormigón y campos de fuerza, solo para ser masacrados cuando la Fundación desplegó anomalías geológicas que fundieron los cimientos de la ciudadela en magma hirviente. Pietro observó de cerca a los comandos de la Fuerza de Tarea Móvil mientras limpiaban los escombros: sus rostros estaban desprovistos de odio, ira o placer; eran autómatas biológicos con una mirada de frialdad quirúrgica, semejantes a cirujanos que amputan una extremidad infectada sin experimentar el menor remordimiento.

En su desesperada travesía hacia el oeste, interceptó transmisiones de radio de pequeños grupos de supervivientes que lloraban en la oscuridad formulando la misma pregunta desgarradora: ¿Por qué? ¿Por qué la organización que dedicó siglos a proteger la normalidad y la vida se convirtió repentinamente en el verdugo implacable de la especie humana? La respuesta a ese misterio se hallaba en una maleta de seguridad hermética que Pietro llevaba asegurada a su espalda: un maletín de titanio que contenía a SCP-055, la anomalía anti-memética absoluta cuya forma y naturaleza nadie puede recordar tras dejar de observarla.

La misión autoimpuesta de Pietro consistía en atravesar las líneas enemigas, alcanzar las ruinas del Sitio-62C y arrojar a SCP-055 dentro del foso de contención de SCP-579, una entidad de distorsión espacio-temporal que, al entrar en contacto con un objeto anti-memético, poseía la capacidad cuántica de reescribir la causalidad y reiniciar la línea temporal del universo.

Durante semanas de marcha infernal a través de tormentas tóxicas y zonas infestadas de monstruos liberados, el traje de Pietro comenzó a fallar críticamente. Los filtros de aire se obstruyeron con polvo radiactivo, los módulos de invisibilidad parpadeaban intermitentemente y sus piernas se llenaron de llagas bajo la presión del blindaje. A pesar del dolor insoportable, la deshidratación y la fiebre delirante, Pietro continuó arrastrándose impulsado por una única convicción: que la humanidad, a pesar de sus errores, sus guerras y sus imperfecciones, merecía una segunda oportunidad de existir.

En sus últimos registros de voz, grabados mientras se arrastraba moribundo por los pasillos inundados de sangre del Sitio-62C, Pietro susurró sus últimas palabras a la grabadora del traje: No sé si lo que descubrió la Fundación en nuestras mentes era verdad. No sé si todos somos recipientes de un monstruo cósmico que devora nuestra alma en la eternidad. Pero sé que sentir empatía, llorar por un amigo y amar a los nuestros no puede ser un error del universo. Si el precio de matar al parásito es destruir todo lo que nos hace humanos, entonces prefiero que el monstruo siga viviendo con nosotros.

Con su último aliento, Pietro Wilson logró arrastrarse hasta el borde del abismo de SCP-579. Abrió el maletín y arrojó el cilindro de SCP-055 a la singularidad gravitacional. El contacto entre ambas anomalías fracturó el tejido del espacio-tiempo, desencadenando una cascada cuántica que reinició la historia del cosmos exactamente antes de que la Fundación descubriera la verdad del Proyecto Pneuma.

En nuestro presente, el traje SCP-5000 apareció materializado de forma espontánea y silenciosa dentro de la cámara de contención del Sitio-62C, con el cuerpo de Pietro Wilson en su interior y todos los archivos intactos. La única marca visible de aquel futuro borrado es una inscripción grabada con un cuchillo en el metal de su casco: ¿Por qué? El Consejo O5 de nuestra realidad mantiene el archivo bajo la clasificación de máxima seguridad Nivel Cinco, asegurando que nadie vuelva a mirar jamás dentro del abismo de la mente humana.
""".strip()


SCP5000_SHORT_SCRIPT = """
En el año 2020, la Fundación SCP cometió el acto más aterrador de su historia: no fue una brecha de contención, fue una decisión unánime. El Consejo O-5 declaró la guerra total contra la humanidad. Liberaron a cada monstruo clasificado: abrieron las celdas de S-C-P 682, enviaron a S-C-P 096 a las capitales del mundo y envenenaron la atmósfera. Los civiles creían que la Fundación los protegía, pero ellos eran ahora los verdugos. Todo comenzó cuando los científicos mapearon el subconsciente humano y descubrieron algo viviendo dentro de cada mente... una entidad parasitaria de dolor absoluto. La única forma de destruirla... era extinguirnos a todos. Un solo técnico sobrevivió dentro del traje anómalo S-C-P 5000 para reiniciar la realidad antes de que el universo colapsara. ¿Tenía razón la Fundación?
""".strip()


async def synthesize_audio(text: str, output_wav: Path, voice: str = "es-MX-JorgeNeural", rate: str = "-3%", pitch: str = "-1Hz") -> float:
    import edge_tts
    logger.info("🎤 Sintetizando audio neural (%s)...", voice)
    temp_mp3 = output_wav.with_suffix(".mp3")
    clean_text = sanitize_script_for_tts(text)
    communicate = edge_tts.Communicate(text=clean_text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(temp_mp3))

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(temp_mp3),
        "-ar", "48000",
        "-ac", "2",
        str(output_wav),
    ]
    subprocess.run(cmd, check=True)
    if temp_mp3.exists():
        temp_mp3.unlink()

    cmd_probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(output_wav)]
    dur_str = subprocess.check_output(cmd_probe, text=True).strip()
    return float(dur_str)


def mix_master_audio(voice_wav: Path, bgm_path: Path, output_audio: Path, total_dur: float, target_lufs: float = -14.0) -> None:
    logger.info("🎛️ Masterizando audio EBU R128 (%.1f LUFS) con sidechain ducking...", target_lufs)
    filter_complex = (
        f"[0:a]aresample=48000,asplit=2[voice_sc][voice_mix];"
        f"[1:a]atrim=0:{total_dur:.3f},aresample=48000,lowpass=f=11000,volume=0.20[bgm_in];"
        f"[bgm_in][voice_sc]sidechaincompress=threshold=0.035:ratio=8.0:attack=20.0:release=350.0:makeup=1[bgm_ducked];"
        f"[voice_mix][bgm_ducked]amix=inputs=2:duration=first:normalize=0[amixed];"
        f"[amixed]loudnorm=I={target_lufs}:TP=-1.5:LRA=11.0,aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
    )
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(voice_wav),
        "-stream_loop", "-1", "-i", str(bgm_path),
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-t", f"{total_dur:.3f}",
        str(output_audio),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 68)
    print("🚀 INICIANDO PRODUCCIÓN CINEMÁTICA 100% EN CÓDIGO MULTI-ESCENA: SCP-5000")
    print("=" * 68 + "\n")

    renderer = MultiActVideoRenderer()

    # =========================================================================
    # PART A: LONGFORM VIDEO (10+ MINUTES, 16:9 FULL HD)
    # =========================================================================
    logger.info(">>> FASE 1: PRODUCCIÓN DEL VIDEO LARGO MULTI-ESCENA (1080P) <<<")
    long_voice_wav = WORK_DIR / "scp5000_long_voice.wav"
    long_master_audio = WORK_DIR / "scp5000_long_master_audio.m4a"
    long_master_video = OUTPUT_DIR / "scp5000_why_longform_1080p.mp4"
    long_thumbnail = OUTPUT_DIR / "scp5000_thumbnail_hd.jpg"
    long_ass_subtitles = WORK_DIR / "scp5000_long_subtitles.ass"

    # Step A1: Voice Synthesis
    long_dur = asyncio.run(synthesize_audio(SCP5000_LONG_SCRIPT, long_voice_wav, voice="es-MX-JorgeNeural", rate="-3%", pitch="-1Hz"))
    logger.info("✅ Audio Largo Generado: %.2f segundos (%.2f minutos)", long_dur, long_dur / 60.0)

    # Step A2: Audio Mastering EBU R128
    mix_master_audio(long_voice_wav, AUDIO_BGM, long_master_audio, long_dur, target_lufs=-14.0)

    # Step A3: High-CTR Thumbnail
    thumb_engine = ResilientThumbnailEngine()
    thumb_engine.generate(
        output_path=long_thumbnail,
        title_main="SCP-5000",
        title_sub="¿POR QUÉ?",
        highlight_box="LA GUERRA DE LA FUNDACIÓN",
        badge_text="NIVEL 5 // ARCHIVO OMNICIDA // CLASIFICADO",
        accent_color=(0, 255, 180),
        subtitle_color=(255, 255, 255),
    )
    logger.info("✅ Miniatura HD 1080p Generada: %s", long_thumbnail.name)

    # Step A4: Multi-Act Narrative Scene Configuration (8 Acts mapped to 5 distinct procedural themes)
    sec_per_act = long_dur / 8.0
    long_acts = [
        NarrativeSceneAct(
            act_index=1,
            start_sec=0 * sec_per_act,
            duration_sec=sec_per_act,
            title="Acto 1: El Hallazgo del Traje SCP-5000 en el Sitio-62C",
            theme_category="act1_suit",
            hud_badge="NIVEL 5 // CLASIFICADO",
            hud_site="SITIO-62C // BÚNKER DE CONTENCIÓN",
            hud_telemetry="TRAJE RECUPERADO // PIETRO WILSON SIN VIDA",
            color_hex="#00FF88",
        ),
        NarrativeSceneAct(
            act_index=2,
            start_sec=1 * sec_per_act,
            duration_sec=sec_per_act,
            title="Acto 2: El Proyecto Pneuma y el Mapeo de la Noosfera",
            theme_category="act2_pneuma",
            hud_badge="ANOMALÍA COGNITIVA // PARÁSITO",
            hud_site="LABORATORIO DE PSICO-ANÁLISIS",
            hud_telemetry="RED NEURONAL GLOBAL // ENTIDAD DETECTADA",
            color_hex="#00E5FF",
        ),
        NarrativeSceneAct(
            act_index=3,
            start_sec=2 * sec_per_act,
            duration_sec=sec_per_act,
            title="Acto 3: La Declaración de Guerra del Consejo O5",
            theme_category="act3_o5",
            hud_badge="ALERTA ROJA // GUERRA DECLARADA",
            hud_site="SALA PLENARIA DEL CONSEJO O5",
            hud_telemetry="DIRECTIVA OMNICIDA TRANSMITIDA // CÓDIGO O5-1",
            color_hex="#FF2244",
        ),
        NarrativeSceneAct(
            act_index=4,
            start_sec=3 * sec_per_act,
            duration_sec=sec_per_act,
            title="Acto 4: El Despliegue Masivo de Anomalías (682, 096, 173)",
            theme_category="act4_monsters",
            hud_badge="BRECHA MASIVA: 682, 096, 173",
            hud_site="SECTORES METROPOLITANOS",
            hud_telemetry="RADAR TÁCTICO // 100% CIUDADES BAJO ATAQUE",
            color_hex="#FFAA00",
        ),
        NarrativeSceneAct(
            act_index=5,
            start_sec=4 * sec_per_act,
            duration_sec=sec_per_act,
            title="Acto 5: La Caída de Ganzir y las Fuerzas de Contención",
            theme_category="act5_ganzir",
            hud_badge="COLAPSO TOTAL // GOC EXTINTA",
            hud_site="FORTALEZA SUBTERRÁNEA GANZIR",
            hud_telemetry="ESTRUCTURA HUNDIDA EN MAGMA // TAREAS MÓVILES",
            color_hex="#FF0055",
        ),
        NarrativeSceneAct(
            act_index=6,
            start_sec=5 * sec_per_act,
            duration_sec=sec_per_act,
            title="Acto 6: La Odisea de Pietro Wilson con la Maleta SCP-055",
            theme_category="act6_desert",
            hud_badge="SOPORTE VITAL: 12% // FILTROS SATURADOS",
            hud_site="DESIERTO RADIACTIVO NORTE",
            hud_telemetry="MALETÍN TITANIO SCP-055 // RUMBO A SITIO-62C",
            color_hex="#00FFCC",
        ),
        NarrativeSceneAct(
            act_index=7,
            start_sec=6 * sec_per_act,
            duration_sec=sec_per_act,
            title="Acto 7: El Sacrificio Final en el Abismo de SCP-579",
            theme_category="act7_vortex",
            hud_badge="DISTORSIÓN HUME CRÍTICA // PARADOJA",
            hud_site="CÁMARA DE CONTENCIÓN SCP-579",
            hud_telemetry="VÓRTICE GRAVITACIONAL // SINGULARIDAD ACTIVA",
            color_hex="#8800FF",
        ),
        NarrativeSceneAct(
            act_index=8,
            start_sec=7 * sec_per_act,
            duration_sec=long_dur - (7 * sec_per_act),
            title="Acto 8: El Reinicio de la Realidad y la Nota: ¿Por Qué?",
            theme_category="act8_helmet",
            hud_badge="RESOLUCIÓN // ARCHIVO SELLADO",
            hud_site="SITIO-62C // PRESENTE",
            hud_telemetry="REALIDAD RESTAURADA // CASCO INSCRITO: ¿POR QUÉ?",
            color_hex="#00FF88",
        ),
    ]

    # Generate ASS Subtitles
    renderer.generate_ass_subtitles(long_acts, long_ass_subtitles, is_vertical=False)

    # Step A5: Multi-Scene Procedural Video Composition
    renderer.composite_multi_act_video(
        acts=long_acts,
        audio_path=long_master_audio,
        output_video=long_master_video,
        total_duration=long_dur,
        is_vertical=False,
        ass_subtitles=long_ass_subtitles,
    )

    # Step A6: SEO Metadata & Synchronized Timestamps
    acts_manifest = [{"start_sec": a.start_sec, "title": a.title} for a in long_acts]
    long_timestamps = SeoOptimizerAgent.build_synchronized_timestamps(acts_manifest, long_dur)
    from src.branding import get_channel_branding
    branding = get_channel_branding("moku")

    long_title = "SCP-5000: ¿Por Qué? - La Guerra de la Fundación contra la Humanidad"
    long_desc = (
        f"{long_title}\n\n"
        "Dentro del Sitio-62C fue hallado un traje mecánico chamuscado con el cadáver de un técnico y una grabación imposible: "
        "la historia de cuando la Fundación SCP decidió exterminar deliberadamente a toda la especie humana tras descubrir un parásito cósmico en el alma humana.\n\n"
        f"{long_timestamps}\n\n"
        f"🔔 Suscríbete a {branding.handle} para más expedientes clasificados y documentales de la Fundación SCP.\n\n"
        "#SCP #SCP5000 #FundacionSCP #TerrorPsicologico #DocumentalSCP #Creepypasta"
    )

    # Step A7: QA Audit
    qa_agent = VisualAudioQAAuditorAgent()
    long_qa = qa_agent.audit_video(
        long_master_video,
        run_id="scp5000_multi_act_longform",
        target_resolution="1920x1080",
        thumbnail_path=long_thumbnail,
        description_text=long_desc,
    )
    logger.info("🔍 QA Audit Longform Score: %d/100 (Overall Pass: %s)", long_qa["quality_score"], long_qa["overall_pass"])

    # =========================================================================
    # PART B: VERTICAL SHORT (9:16, 1080x1920, 49s)
    # =========================================================================
    logger.info("\n>>> FASE 2: PRODUCCIÓN DEL SHORT VERTICAL MULTI-ESCENA (1080x1920) <<<")
    short_voice_wav = WORK_DIR / "scp5000_short_voice.wav"
    short_master_audio = WORK_DIR / "scp5000_short_master_audio.m4a"
    short_master_video = OUTPUT_DIR / "scp5000_why_short_1080x1920.mp4"
    short_thumbnail = OUTPUT_DIR / "scp5000_short_thumbnail.jpg"
    short_ass_subtitles = WORK_DIR / "scp5000_short_subtitles.ass"

    # Step B1: Short Voice Synthesis (Dynamic +15% rate)
    short_dur = asyncio.run(synthesize_audio(SCP5000_SHORT_SCRIPT, short_voice_wav, voice="es-MX-JorgeNeural", rate="+15%", pitch="-1Hz"))
    logger.info("✅ Audio Short Generado: %.2f segundos", short_dur)

    # Step B2: Audio Mastering
    mix_master_audio(short_voice_wav, AUDIO_BGM, short_master_audio, short_dur, target_lufs=-14.0)

    # Step B3: Short Vertical Thumbnail
    thumb_engine.generate(
        output_path=short_thumbnail,
        title_main="SCP-5000",
        title_sub="TRAICIÓN",
        highlight_box="GUERRA TOTAL",
        badge_text="SHORTS // CLASIFICADO",
        accent_color=(255, 60, 80),
        width=1080,
        height=1920,
    )

    # Step B4: Short Dynamic Multi-Cut Acts (3 Visual Scenes in 49 seconds)
    cut_dur = short_dur / 3.0
    short_acts = [
        NarrativeSceneAct(
            act_index=1,
            start_sec=0.0,
            duration_sec=cut_dur,
            title="LA GUERRA DE LA FUNDACIÓN",
            theme_category="short1_suit",
            hud_badge="SHORTS // CLASIFICADO",
            hud_site="CONSEJO O5 // DECLARACIÓN",
            color_hex="#00FF88",
        ),
        NarrativeSceneAct(
            act_index=2,
            start_sec=cut_dur,
            duration_sec=cut_dur,
            title="ANOMALÍAS LIBERADAS: 682 & 096",
            theme_category="short2_monsters",
            hud_badge="BRECHA TOTAL",
            hud_site="COLAPSO GLOBAL",
            color_hex="#FF2244",
        ),
        NarrativeSceneAct(
            act_index=3,
            start_sec=cut_dur * 2,
            duration_sec=short_dur - (cut_dur * 2),
            title="SCP-5000: ¿POR QUÉ?",
            theme_category="short3_vortex",
            hud_badge="REINICIO CUÁNTICO",
            hud_site="ABISMO SCP-579",
            color_hex="#8800FF",
        ),
    ]

    # Generate ASS Subtitles for Short
    renderer.generate_ass_subtitles(short_acts, short_ass_subtitles, is_vertical=True)

    # Step B5: Multi-Scene Short Composition
    renderer.composite_multi_act_video(
        acts=short_acts,
        audio_path=short_master_audio,
        output_video=short_master_video,
        total_duration=short_dur,
        is_vertical=True,
        ass_subtitles=short_ass_subtitles,
    )

    # Step B6: QA Audit for Short
    short_qa = qa_agent.audit_video(
        short_master_video,
        run_id="scp5000_multi_act_short",
        target_resolution="1080x1920",
        thumbnail_path=short_thumbnail,
    )
    logger.info("🔍 QA Audit Short Score: %d/100 (Overall Pass: %s)", short_qa["quality_score"], short_qa["overall_pass"])

    # Cleanup temporary work directory
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)

    print("\n" + "=" * 68)
    print("🎉 ¡PRODUCCIÓN MULTI-ESCENA EN CÓDIGO COMPLETADA EXITOSAMENTE!")
    print("=" * 68)
    print(f"🎬 VIDEO LARGO (16:9 Multi-Escena): {long_master_video}")
    print(f"   ⏱️ Duración:        {int(long_dur // 60)}m {int(long_dur % 60):02d}s ({long_dur:.2f}s)")
    print(f"   📐 Resolución:      1920x1080 Full HD (8 Actos Procedurales)")
    print(f"   🖼️ Miniatura:       {long_thumbnail}")
    print(f"   🎯 QA Score:        {long_qa['quality_score']}/100")
    print("-" * 68)
    print(f"📱 SHORT VERTICAL (9:16 Multi-Corte): {short_master_video}")
    print(f"   ⏱️ Duración:        {int(short_dur // 60)}m {int(short_dur % 60):02d}s ({short_dur:.2f}s)")
    print(f"   📐 Resolución:      1080x1920 Vertical (3 Actos Procedurales)")
    print(f"   🖼️ Miniatura:       {short_thumbnail}")
    print(f"   🎯 QA Score:        {short_qa['quality_score']}/100")
    print("=" * 68 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
