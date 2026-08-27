"""
Unit tests for INarrativeCurator Strategy Pattern and NarrativeDirector.
"""

import pytest
from src.curators import get_narrative_director, MokuHorrorCurator, AelithiaDramaCurator
from src.core.domain import CanonicalChannel


def test_narrative_director_registration_and_retrieval():
    director = get_narrative_director()
    moku_curator = director.get_curator("moku")
    assert isinstance(moku_curator, MokuHorrorCurator)
    assert moku_curator.channel == "moku"

    aelithia_curator = director.get_curator("aelithia")
    assert isinstance(aelithia_curator, AelithiaDramaCurator)
    assert aelithia_curator.channel == "aelithia"


def test_narrative_director_aliases():
    director = get_narrative_director()
    assert isinstance(director.get_curator("terror"), MokuHorrorCurator)
    assert isinstance(director.get_curator("scp"), MokuHorrorCurator)
    assert isinstance(director.get_curator("drama"), AelithiaDramaCurator)
    assert isinstance(director.get_curator("soy_el_malo"), AelithiaDramaCurator)
    assert isinstance(director.get_curator(CanonicalChannel.MOKU), MokuHorrorCurator)
    assert isinstance(director.get_curator(CanonicalChannel.AELITHIA), AelithiaDramaCurator)


def test_moku_curator_short_scp():
    curator = MokuHorrorCurator()
    script = curator.build_short_narrative("SCP-173")
    assert "SCP-173" in script
    assert "Euclid" in script or "escultura" in script
    assert "@Moku" in script


def test_aelithia_curator_short():
    curator = AelithiaDramaCurator()
    script = curator.build_short_narrative("Herencia familiar en disputa")
    assert "¿Soy yo el malo" in script
    assert "SCP" not in script
    assert "@Aelithia" in script


def test_organic_connectors():
    moku = MokuHorrorCurator()
    aelithia = AelithiaDramaCurator()

    m_conn = moku.get_organic_connectors()
    a_conn = aelithia.get_organic_connectors()

    assert len(m_conn) >= 3
    assert len(a_conn) >= 3
    assert any("estación" in c or "sensores" in c or "noche" in c for c in m_conn)
    assert any("familia" in c or "decisión" in c or "reunión" in c for c in a_conn)
