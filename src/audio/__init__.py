"""
src/audio - Cosmic & Analog Horror Audio Engine package.
"""
from src.audio.procedural_drone import ProceduralDroneSynthesizer
from src.audio.vocal_chain import VocalChainProcessor
from src.audio.sfx_library import SFXLibrarySynthesizer
from src.audio.mixer import CosmicAudioMixer

__all__ = [
    "ProceduralDroneSynthesizer",
    "VocalChainProcessor",
    "SFXLibrarySynthesizer",
    "CosmicAudioMixer",
]
