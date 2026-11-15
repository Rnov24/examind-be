"""AI question generation: model fallback chain, dedup, top-up, provenance.

Direction (Jal, 2026-11-15): NO template answers. If every model fails,
generate_questions raises an honest 503 — it must never serve mock
template questions. The mock adapter is out of scope here on purpose.
"""

import json

import pytest

from app.core.exceptions import AppException
from app.schemas.question import (
    AIGenerateRequest,
    GeneratedQuestionEssay,
    GeneratedQuestionMCQ,
    OptionSchema,
)
from app.services.ai import provider_router
from app.services.ai.dedup import dedupe_essays, dedupe_mcqs, stem_similarity
from app.services.ai.gemini_adapter import GeminiAdapter, gemini_ai_service
from app.services.ai.mock_adapter import mock_ai_service

_CFG = {
    "provider": "gemini",
    "model": "gemini-2.5-flash",
    "temperature": 0.7,
    "max_tokens": 4096,
    "providers_supported": ["gemini", "openai", "claude", "deepseek", "ollama"],
    "api_key": "",
    "configured": False,
}


def _mcq_json(prompt, correct="B", texts=None):
    # Default option texts are derived from the prompt so fixtures do not
    # accidentally share an identical option-text set (dedup would rightly
    # drop them as the same item). Pass explicit `texts` when the test
    # wants to control the option set.
    if texts is None:
        tag = prompt[:16].strip()
        texts = [f"Jawaban {letter} terkait {tag}" for letter in "ABCD"]
    opts = [
        {"id": letter, "text": text, "is_correct": letter == correct, "rationale": f"Alasan {letter}"}
        for letter, text in zip("ABCD", texts)
    ]
    return {
        "prompt": prompt,
        "difficulty": "medium",
        "bloom_level": "C3",
        "options": opts,
        "correct_option_id": correct,
        "explanation": f"Pembahasan: {prompt[:30]}",
        "points": 10.0,
    }


def _essay_json(prompt):
    return {
        "prompt": prompt,
        "difficulty": "medium",
        "bloom_level": "C4",
        "sample_answer": "Jawaban acuan ringkas.",
        "ref_points": [
            {"id": "p1", "statement": "Konsep inti", "weight": 0.5},
            {"id": "p2", "statement": "Argumen dan bukti", "weight": 0.5},
        ],
        "rubric": {},
        "points": 20.0,
    }


def _mcq(prompt, texts, explanation="x"):
    opts = [
        OptionSchema(id=letter, text=text, is_correct=letter == "A", rationale="r")
        for letter, text in zip("ABCD", texts)
    ]
    return GeneratedQuestionMCQ(
        prompt=prompt, difficulty="medium", bloom_level="C3",
        options=opts, correct_option_id="A", explanation=explanation, points=10.0,
    )


def _essay(prompt):
    return GeneratedQuestionEssay(
        prompt=prompt, difficulty="hard", bloom_level="C4",
        rubric={}, ideal_answer="acuan", explanation="e", points=20.0,
    )


def _stub_try_provider(calls, behaviour):
    """behaviour: provider -> 'gemini_fn' | 'fail' | JSON string."""
    def stub(provider, config, message, history, system_instruction,
             temperature, timeout_seconds, json_mode, gemini_fn, user=None, db=None):
        calls.append({
            "provider": provider, "temperature": temperature,
            "json_mode": json_mode, "message": message,
        })
        mode = behaviour.get(provider, "fail")
        if mode == "gemini_fn":
            return gemini_fn()
        if mode == "fail":
            return None
        return mode
    return stub


# ---------------------------------------------------------------------------
# (a) All models fail -> honest 503, mock never touched
# ---------------------------------------------------------------------------

def test_all_models_fail_raises_and_never_touches_mock(monkeypatch):
    calls = []
    monkeypatch.setattr(provider_router, "get_task_config", lambda tid: dict(_CFG))
    monkeypatch.setattr(
        provider_router, "_try_provider",
        _stub_try_provider(calls, {"gemini": "gemini_fn"}),
    )
    monkeypatch.setattr(GeminiAdapter, "_call_gemini", lambda *a, **k: None)

    def _boom(req):
        raise AssertionError("mock generate_questions must never be called")

    monkeypatch.setattr(mock_ai_service, "generate_questions", _boom)

    with pytest.raises(AppException) as exc_info:
        gemini_ai_service.generate_questions(AIGenerateRequest(
            subject="Biologi", topic_content="Fotosintesis", mcq_count=3, essay_count=1,
        ))
    assert exc_info.value.status_code == 503
    assert exc_info.value.error_code == "AI_SERVICE_UNAVAILABLE"
    # Every configured model tried once, configured provider first.
    assert [c["provider"] for c in calls] == ["gemini", "openai", "claude", "deepseek", "ollama"]


# ---------------------------------------------------------------------------
# (b) Gemini fails, second model serves -> provider records the second model
# ---------------------------------------------------------------------------

def test_gemini_fails_second_model_serves_and_provider_records_it(monkeypatch):
    calls = []
    good = json.dumps({
        "mcq_questions": [
            _mcq_json("Apa fungsi utama klorofil dalam fotosintesis?"),
            _mcq_json("Mengapa tumbuhan memerlukan cahaya matahari?"),
        ],
        "essay_questions": [_essay_json("Jelaskan proses fotosintesis!")],
    })
    monkeypatch.setattr(provider_router, "get_task_config", lambda tid: dict(_CFG))
    monkeypatch.setattr(
        provider_router, "_try_provider",
        _stub_try_provider(calls, {"gemini": "gemini_fn", "openai": good}),
    )
    monkeypatch.setattr(GeminiAdapter, "_call_gemini", lambda *a, **k: None)

    res = gemini_ai_service.generate_questions(AIGenerateRequest(
        subject="Biologi", topic_content="Fotosintesis", mcq_count=2, essay_count=1,
    ))
    assert res.provider == "openai"
    assert len(res.mcq_questions) == 2
    assert len(res.essay_questions) == 1
    assert [c["provider"] for c in calls] == ["gemini", "openai"]
    assert calls[1]["temperature"] == 0.7


# ---------------------------------------------------------------------------
# Temperature comes from the task config, not hardcoded 0.2
# ---------------------------------------------------------------------------

def test_temperature_comes_from_task_config(monkeypatch):
    cfg = dict(_CFG, temperature=0.9)
    monkeypatch.setattr(provider_router, "get_task_config", lambda tid: dict(cfg))
    seen = {}

    def stub_try(provider, config, message, history, system_instruction,
                 temperature, timeout_seconds, json_mode, gemini_fn, user=None, db=None):
        seen["try_provider_temp"] = temperature
        if provider == "gemini":
            return gemini_fn()
        return None

    monkeypatch.setattr(provider_router, "_try_provider", stub_try)

    def fake_call(self, prompt=None, contents=None, system_instruction=None,
                  json_mode=False, temperature=0.2, api_key=None, **kw):
        seen["gemini_temp"] = temperature
        return json.dumps({"mcq_questions": [_mcq_json("Satu soal unik?")], "essay_questions": []})

    monkeypatch.setattr(GeminiAdapter, "_call_gemini", fake_call)

    res = gemini_ai_service.generate_questions(AIGenerateRequest(
        subject="Fisika", topic_content="Gaya", mcq_count=1, essay_count=0,
    ))
    assert seen["try_provider_temp"] == 0.9
    assert seen["gemini_temp"] == 0.9
    assert res.provider == "gemini"


# ---------------------------------------------------------------------------
# (c) Dedup + one model top-up
# ---------------------------------------------------------------------------

def test_dedup_and_model_top_up(monkeypatch):
    monkeypatch.setattr(provider_router, "get_task_config", lambda tid: dict(_CFG))
    dup_batch = json.dumps({"mcq_questions": [
        _mcq_json("Apa fungsi utama klorofil?"),
        _mcq_json("Apa fungsi utama klorofil?"),
        _mcq_json("Mengapa tumbuhan memerlukan cahaya?"),
    ], "essay_questions": []})
    fresh_batch = json.dumps({"mcq_questions": [
        _mcq_json("Bagaimana laju fotosintesis dipengaruhi intensitas cahaya?"),
    ], "essay_questions": []})
    script = [dup_batch, fresh_batch]
    calls = []

    def stub_try(provider, config, message, history, system_instruction,
                 temperature, timeout_seconds, json_mode, gemini_fn, user=None, db=None):
        calls.append({"provider": provider, "message": message})
        return script.pop(0) if script else None

    monkeypatch.setattr(provider_router, "_try_provider", stub_try)

    res = gemini_ai_service.generate_questions(AIGenerateRequest(
        subject="Biologi", topic_content="Fotosintesis", mcq_count=3, essay_count=0,
    ))
    assert len(res.mcq_questions) == 3
    assert len({q.prompt for q in res.mcq_questions}) == 3
    assert len(calls) == 2
    # The top-up prompt lists the kept stems so the model does not repeat them.
    assert "Apa fungsi utama klorofil?" in calls[1]["message"]
    assert res.provider == "gemini"


def test_top_up_failure_returns_partial_distinct_set(monkeypatch):
    monkeypatch.setattr(provider_router, "get_task_config", lambda tid: dict(_CFG))
    dup_batch = json.dumps({"mcq_questions": [
        _mcq_json("Apa fungsi utama klorofil?"),
        _mcq_json("Apa fungsi utama klorofil?"),
        _mcq_json("Mengapa tumbuhan memerlukan cahaya?"),
    ], "essay_questions": []})
    calls = []

    def stub_try(provider, config, message, history, system_instruction,
                 temperature, timeout_seconds, json_mode, gemini_fn, user=None, db=None):
        calls.append(provider)
        if len(calls) == 1:
            return dup_batch
        return None

    monkeypatch.setattr(provider_router, "_try_provider", stub_try)

    res = gemini_ai_service.generate_questions(AIGenerateRequest(
        subject="Biologi", topic_content="Fotosintesis", mcq_count=3, essay_count=0,
    ))
    # No padding with duplicates, no error: the distinct set it has.
    assert len(res.mcq_questions) == 2
    assert len({q.prompt for q in res.mcq_questions}) == 2
    assert res.provider == "gemini"


def test_unparseable_first_model_falls_through_to_next(monkeypatch):
    monkeypatch.setattr(provider_router, "get_task_config", lambda tid: dict(_CFG))
    good = json.dumps({"mcq_questions": [_mcq_json("Soal yang valid?")], "essay_questions": []})
    monkeypatch.setattr(
        provider_router, "_try_provider",
        _stub_try_provider([], {"gemini": "bukan json {", "openai": good}),
    )
    monkeypatch.setattr(GeminiAdapter, "_call_gemini", lambda *a, **k: None)

    res = gemini_ai_service.generate_questions(AIGenerateRequest(
        subject="Fisika", topic_content="Gaya", mcq_count=1, essay_count=0,
    ))
    assert res.provider == "openai"
    assert res.mcq_questions[0].prompt == "Soal yang valid?"


# ---------------------------------------------------------------------------
# Dedup unit tests
# ---------------------------------------------------------------------------

def test_dedup_exact_duplicate_dropped():
    a = _mcq("Apa fungsi klorofil dalam fotosintesis?", ["a1", "b1", "c1", "d1"])
    b = _mcq("Apa fungsi klorofil dalam fotosintesis?", ["a2", "b2", "c2", "d2"])
    c = _mcq("Mengapa tumbuhan memerlukan cahaya matahari?", ["a3", "b3", "c3", "d3"])
    out = dedupe_mcqs([a, b, c])
    assert len(out) == 2
    assert out[0] is a and out[1] is c


def test_dedup_paraphrase_dropped_first_kept():
    a = _mcq("Manakah analisis komparatif yang paling tepat mengenai fotosintesis?",
             ["a1", "b1", "c1", "d1"], explanation="first")
    b = _mcq("Analisis komparatif manakah yang tepat tentang fotosintesis?",
             ["a2", "b2", "c2", "d2"], explanation="second")
    assert stem_similarity(a.prompt, b.prompt) >= 0.5
    out = dedupe_mcqs([a, b])
    assert len(out) == 1
    assert out[0].explanation == "first"


def test_dedup_distinct_questions_kept():
    qs = [
        _mcq("Apa fungsi utama klorofil dalam fotosintesis?", ["a1", "b1", "c1", "d1"]),
        _mcq("Mengapa tumbuhan memerlukan cahaya matahari?", ["a2", "b2", "c2", "d2"]),
        _mcq("Bagaimana laju fotosintesis dipengaruhi intensitas cahaya?", ["a3", "b3", "c3", "d3"]),
    ]
    out = dedupe_mcqs(qs)
    assert len(out) == 3


def test_dedup_identical_option_set_dropped():
    a = _mcq("Soal tentang fungsi?", ["sama1", "sama2", "sama3", "sama4"])
    b = _mcq("Soal tentang struktur?", ["sama4", "sama3", "sama2", "sama1"])
    out = dedupe_mcqs([a, b])
    assert len(out) == 1


def test_dedup_essays_paraphrase_dropped_distinct_kept():
    a = _essay("Jelaskan secara mendalam konsep fundamental mengenai fotosintesis!")
    b = _essay("Jelaskan konsep fundamental fotosintesis secara mendalam!")
    c = _essay("Bandingkan fotosintesis dengan respirasi sel!")
    out = dedupe_essays([a, b, c])
    assert len(out) == 2
    assert out[0] is a and out[1] is c
