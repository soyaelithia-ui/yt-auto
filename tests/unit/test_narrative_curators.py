"""
Unit tests for INarrativeCurator Strategy Pattern and NarrativeDirector.
"""

import pytest
from src.curators import get_narrative_director, HorrorCurator, DramaCurator
from src.core.domain import CanonicalChannel


def test_narrative_director_registration_and_retrieval():
    director = get_narrative_director()
    horror_curator = director.get_curator("horror")
    assert isinstance(horror_curator, HorrorCurator)
    assert horror_curator.channel == "horror"

    drama_curator = director.get_curator("drama")
    assert isinstance(drama_curator, DramaCurator)
    assert drama_curator.channel == "drama"


def test_narrative_director_aliases():
    director = get_narrative_director()
    assert isinstance(director.get_curator("terror"), HorrorCurator)
    assert isinstance(director.get_curator("drama"), DramaCurator)
    assert isinstance(director.get_curator("soy_el_malo"), DramaCurator)
    assert isinstance(director.get_curator(CanonicalChannel.HORROR), HorrorCurator)
    assert isinstance(director.get_curator(CanonicalChannel.DRAMA), DramaCurator)


def test_horror_curator_short_scp():
    curator = HorrorCurator()
    script = curator.build_short_narrative("SCP-173")
    assert "SCP-173" in script
    assert "Euclid" in script or "escultura" in script
    assert "parpadeo" in script or "parpadees" in script


def test_drama_curator_short():
    curator = DramaCurator()
    script = curator.build_short_narrative("Herencia familiar en disputa")
    assert "¿Soy yo el malo" in script
    assert "SCP" not in script
    assert "comentarios" in script


def test_organic_connectors():
    horror = HorrorCurator()
    drama = DramaCurator()

    h_conn = horror.get_organic_connectors()
    d_conn = drama.get_organic_connectors()

    assert len(h_conn) >= 3
    assert len(d_conn) >= 3
    assert any("estación" in c or "sensores" in c or "noche" in c for c in h_conn)
    assert any("familia" in c or "decisión" in c or "reunión" in c for c in d_conn)
