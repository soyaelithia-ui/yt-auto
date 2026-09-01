"""Adversarial stress test for Challenge 3: Sanitizer Edge Cases & Robustness."""
import time
import pytest
from src.sanitizer import (
    strip_ass_tags,
    strip_act_chapter_headers,
    sanitize_scp_acronyms_for_tts,
    limpiar_texto_para_tts,
    sanitize_script_text,
    sanitize_html_entities,
    validate_pre_tts_script,
    validate_semantic_barrier,
    strip_llm_prompt_leaks,
    PromptLeakError,
    RE_ACT_CHAPTER_LABELS,
)
from lib.tts import strip_markdown_for_tts, sanitize_text_for_tts

# ---------------------------------------------------------------------------
# 1. ASS Subtitle Tag Stripping Edge Cases
# ---------------------------------------------------------------------------
def test_strip_ass_tags_edge_cases():
    assert strip_ass_tags(None) == ""
    assert strip_ass_tags("") == ""
    assert strip_ass_tags("   ") == "   "
    
    # Standard and complex ASS tags
    sample = r"{\k50}Hola {\pos(192,1080)\c&H0000FF&}Mundo{\r}"
    assert strip_ass_tags(sample) == "Hola Mundo"
    
    # Multiple adjacent tags
    sample2 = r"{\b1}{\i1}{\u1}{\fs30\fnArial}Texto Complejo{\r}"
    assert strip_ass_tags(sample2) == "Texto Complejo"
    
    # Text without ASS tags
    sample3 = "Normal text without tags"
    assert strip_ass_tags(sample3) == sample3

# ---------------------------------------------------------------------------
# 2. Chapter & Structural Header Stripping (Roman, Ordinal, Digits)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("header_input, expected_clean", [
    ("Capítulo 1: El despertar de la bestia", "El despertar de la bestia"),
    ("Capítulo IV: La noche oscura", "La noche oscura"),
    ("CAPÍTULO XIV - Sombras en el sótano", "Sombras en el sótano"),
    ("Capítulo XLVIII: La última frontera", "La última frontera"),
    ("Sección primera: Los antecedentes", "Los antecedentes"),
    ("Sección Segunda - La criatura", "La criatura"),
    ("Parte Tercera: El desenlace", "El desenlace"),
    ("Paso Cuarto: La contención", "La contención"),
    ("Fase Quinta: Evacuación total", "Evacuación total"),
    ("Bloque Sexto: Análisis forense", "Análisis forense"),
    ("Acto I: Inicio del fin", "Inicio del fin"),
    ("Acto 3: La caída", "La caída"),
    ("### Capítulo 7: El ritual\nEl cuerpo yacía en el altar.", "El cuerpo yacía en el altar."),
    ("Título: La Mansión Encantada\nLas puertas se abrieron.", "Las puertas se abrieron."),
    ("Title: The Haunted Mansion\nThe doors were open.", "The doors were open."),
])
def test_strip_act_chapter_headers_edge_cases(header_input, expected_clean):
    cleaned = strip_act_chapter_headers(header_input)
    assert cleaned == expected_clean

def test_roman_numerals_exhaustive():
    """Verify various roman numerals in chapter headers."""
    roman_numerals = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", 
                      "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
                      "XXV", "XXX", "XL", "XLV", "L", "LX", "LXX", "LXXX", "XC", "XCIX"]
    for rn in roman_numerals:
        raw = f"Capítulo {rn}: Relato número {rn}"
        cleaned = strip_act_chapter_headers(raw)
        assert f"Capítulo {rn}" not in cleaned
        assert cleaned == f"Relato número {rn}"

def test_acto_spacing_edge_case_behavior():
    """
    Adversarial finding: RE_ACT_CHAPTER_LABELS strips 'Acto 1:' and 'Acto 1-La caída'
    but requires no space before '-' because of pattern:
    r'(?i)\b(?:acto|cap[ií]tulo|secci[oó]n|parte)\s+[a-záéíóú0-9IVXLCDMivxlcdm]+[:\.\-–—]\s*'
    """
    assert strip_act_chapter_headers("Acto 1: La caída") == "La caída"
    assert strip_act_chapter_headers("Acto 1- La caída") == "La caída"
    # Document current regex behavior on space before dash
    res_space_dash = strip_act_chapter_headers("Acto 1 - La caída")
    assert res_space_dash == "Acto 1 - La caída"

# ---------------------------------------------------------------------------
# 3. SCP Acronym Sanitization Edge Cases
# ---------------------------------------------------------------------------
def test_sanitize_scp_acronyms():
    assert sanitize_scp_acronyms_for_tts(None) == ""
    assert sanitize_scp_acronyms_for_tts("") == ""
    
    raw = "El consejo O5 activó el dispositivo XACTS para contener a SCP-682 y prevenir un evento XK con BZHR."
    cleaned = sanitize_scp_acronyms_for_tts(raw)
    
    assert "O-5" in cleaned
    assert "X-ACTS" in cleaned
    assert "S-C-P 682" in cleaned
    assert "X-K" in cleaned
    assert "B-Z-H-R" in cleaned
    assert "SCP-682" not in cleaned

# ---------------------------------------------------------------------------
# 4. Markdown Stripping & Limpiar Texto Para TTS
# ---------------------------------------------------------------------------
def test_limpiar_texto_para_tts_markdown_and_sfx():
    raw = (
        "```python\n# Hidden code\n```\n"
        "# Título Principal\n\n"
        "## Capítulo 1: El Enigma\n\n"
        "[Sonido: Trueno lejano]\n"
        "SFX 1: Viento soplando fuertemente.\n"
        "Era una noche **extremadamente** oscura y *silenciosa*.\n"
        "Visita [nuestro sitio](https://example.com) para más detalles.\n"
        "> Advertencia importante: No abrir la puerta.\n"
    )
    cleaned = limpiar_texto_para_tts(raw)
    
    assert "python" not in cleaned
    assert "Hidden code" not in cleaned
    assert "Título Principal" not in cleaned
    assert "Capítulo 1" not in cleaned
    assert "Sonido:" not in cleaned
    assert "SFX 1:" not in cleaned
    assert "https://example.com" not in cleaned
    assert "nuestro sitio" in cleaned
    assert "Advertencia importante: No abrir la puerta." in cleaned

def test_strip_markdown_for_tts():
    raw = "Era una noche **extremadamente** oscura y *silenciosa*."
    cleaned = strip_markdown_for_tts(raw)
    assert cleaned == "Era una noche extremadamente oscura y silenciosa."

def test_full_sanitize_text_for_tts_pipeline():
    raw = (
        "### Capítulo 1: La Llegada\n"
        "[Sonido: Pasos en la madera]\n"
        "La criatura se movía a 120 km/h en r/nosleep. "
        "Era **muy** peligrosa."
    )
    cleaned = sanitize_text_for_tts(raw)
    assert "Capítulo 1" not in cleaned
    assert "Sonido:" not in cleaned
    assert "kilómetros por hora" in cleaned
    assert "sub reddit nosleep" in cleaned
    assert "muy peligrosa" in cleaned
    assert "*" not in cleaned

# ---------------------------------------------------------------------------
# 5. HTML Entities and Split Accents
# ---------------------------------------------------------------------------
def test_html_entities_and_split_accents():
    raw = "Hab&iacute; a una vez en la habitaci&oacute; n &nbsp; un misterio &amp; terror.<br/>"
    cleaned = sanitize_script_text(raw)
    assert "había" in cleaned.lower()
    assert "habitación" in cleaned.lower()
    assert "&" in cleaned
    assert "<br" not in cleaned

# ---------------------------------------------------------------------------
# 6. ReDoS / Catastrophic Backtracking Stress Test
# ---------------------------------------------------------------------------
def test_regex_catastrophic_backtracking_resilience():
    """Verify that very long and repetitive adversarial inputs do not freeze regex engine."""
    # 50,000 characters of repetitive patterns with narrative body
    adversarial_payload = ("### Capítulo " + "X" * 100 + ": " + "palabra " * 100 + "\nNarración principal aquí.\n") * 20
    
    t0 = time.time()
    cleaned = limpiar_texto_para_tts(adversarial_payload)
    elapsed = time.time() - t0
    
    # Must complete in under 2.0 seconds without ReDoS
    assert elapsed < 2.0, f"Regex processing took too long: {elapsed:.2f}s (Possible ReDoS)"
    assert "Narración principal aquí" in cleaned

# ---------------------------------------------------------------------------
# 7. Semantic Barrier & Prompt Leak Errors
# ---------------------------------------------------------------------------
def test_prompt_leak_detection():
    leak_examples = [
        "El usuario quiere que cuentes una historia de terror.",
        "Aquí tienes tu guion para el locutor.",
        "tono documental sin headers",
        "reglas obligatorias para el locutor",
        "system prompt activo",
        "espero que te sirva el guion",
    ]
    for leak in leak_examples:
        with pytest.raises(PromptLeakError):
            validate_pre_tts_script(leak)

def test_clean_script_passes_validation():
    clean_script = "En lo profundo del bosque, una silueta inmóvil observaba la cabaña bajo la lluvia incesante."
    assert validate_pre_tts_script(clean_script) is True

if __name__ == "__main__":
    pytest.main(["-v", __file__])
