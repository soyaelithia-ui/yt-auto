"""
src/templates/longform_stories_ext.py - Extended multi-storyline library for longform narratives.
Loads externalized storyline templates from config/templates/ ensuring modularity and low token overhead.
"""
from __future__ import annotations

from typing import Any

from src.templates.loader import load_template_json, render_paragraphs


def build_moku_deepsea(topic: str, **kwargs: Any) -> str:
    """Story 4: Deep-Sea Trench Exploration (Abyssal Submersible)."""
    tpl = load_template_json("longform_stories_moku.json")
    return render_paragraphs(tpl["deepsea"], {"topic": topic})


def build_moku_asylum(topic: str, **kwargs: Any) -> str:
    """Story 5: Abandoned Psychiatric Sanitarium Inspection."""
    tpl = load_template_json("longform_stories_moku.json")
    return render_paragraphs(tpl["asylum"], {"topic": topic})


def build_moku_observatory(topic: str, **kwargs: Any) -> str:
    """Story 6: High-Altitude Astronomical Observatory Anomaly."""
    tpl = load_template_json("longform_stories_moku.json")
    return render_paragraphs(tpl["observatory"], {"topic": topic})


def build_moku_saltmine(topic: str, **kwargs: Any) -> str:
    """Story 7: Subterranean Salt Mine Excavation Breach."""
    tpl = load_template_json("longform_stories_moku.json")
    return render_paragraphs(tpl["saltmine"], {"topic": topic})


def build_aelithia_secret_inheritance(topic: str, **kwargs: Any) -> str:
    """Story 4: Secret Estate Inheritance & Entitled Relatives."""
    tpl = load_template_json("longform_stories_aelithia.json")
    return render_paragraphs(tpl["secret_inheritance"], {"topic": topic})


def build_aelithia_fake_fundraiser(topic: str, **kwargs: Any) -> str:
    """Story 5: Fraudulent Medical Crowdfunding Exposure."""
    tpl = load_template_json("longform_stories_aelithia.json")
    return render_paragraphs(tpl["fake_fundraiser"], {"topic": topic})


def build_aelithia_property_usurpation(topic: str, **kwargs: Any) -> str:
    """Story 6: Family Squatting & Eviction Lawsuit."""
    tpl = load_template_json("longform_stories_aelithia.json")
    return render_paragraphs(tpl["property_usurpation"], {"topic": topic})


def build_aelithia_adoption_extortion(topic: str, **kwargs: Any) -> str:
    """Story 7: Child Custody & Biological Blackmail."""
    tpl = load_template_json("longform_stories_aelithia.json")
    return render_paragraphs(tpl["adoption_extortion"], {"topic": topic})
