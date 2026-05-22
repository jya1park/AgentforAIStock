"""Smoke test that the generator prompt templates format correctly.

KeyError on str.format() has bitten us once already — adding placeholders
to the prompt body without escaping the braces breaks the live call but
not any unit test that doesn't actually exercise the format path. This
file fixes that hole.
"""

from evals import generators


def test_payload_perturb_prompt_formats_without_keyerror():
    """The payload-perturb prompt body uses {n} and {baseline}; any other
    single-brace token (e.g. literal '{total}') would raise KeyError."""
    out = generators._PAYLOAD_PERTURB_PROMPT.format(n=10, baseline="...example payload...")
    assert "produce 10 variants" in out
    assert "example payload" in out


def test_question_perturb_prompt_formats_without_keyerror():
    out = generators._QUESTION_PERTURB_PROMPT.format(n=30)
    assert "30 chatbot test questions" in out
