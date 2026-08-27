"""
src/agents/__init__.py - Native Multi-Agent Pipeline package.
"""
from src.agents.base_agent import CANONICAL_MODEL, ProgrammaticAgent
from src.agents.script_curator import CinematicScriptCuratorAgent
from src.agents.art_director import ArtDirectorMoodAgent
from src.agents.scene_planner import ScenePlannerCompositorAgent
from src.agents.qa_auditor import VisualAudioQAAuditorAgent
from src.agents.investigator import StoryInvestigatorAgent, generate_story_script
from src.agents.translator import TranslatorAgent
from src.agents.image_auditor import ImageAuditorAgent
from src.agents.seo_optimizer import SeoOptimizerAgent

__all__ = [
    "CANONICAL_MODEL",
    "ProgrammaticAgent",
    "CinematicScriptCuratorAgent",
    "ArtDirectorMoodAgent",
    "ScenePlannerCompositorAgent",
    "VisualAudioQAAuditorAgent",
    "StoryInvestigatorAgent",
    "generate_story_script",
    "TranslatorAgent",
    "ImageAuditorAgent",
    "SeoOptimizerAgent",
]
