"""api.normalize 단위 테스트.

전략
----
sentence-transformers 모델은 ~120MB라 CI에서 매 번 받기 부담스럽다.
그래서 테스트를 2층으로 구성한다:

1. **Mock layer** (기본, 항상 실행): _encode를 monkeypatch해서 결정론적
   벡터로 대체. 실제 모델 로드·다운로드 없음. CI에서 빠르게 통과.

2. **Disable layer**: NORMALIZE_DISABLE=1 환경변수에서 find_canonical_name이
   None을 반환하는지 확인.

3. **Optional real-model layer** (기본 skip): RUN_REAL_EMBEDDING=1일 때만
   실제 모델을 로드해서 "Remote Control" ≈ "remote control", "음성 인식" ≈
   "음성인식 기술" 같은 실전 케이스를 확인. 로컬·수동 검증용.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api import normalize


# ── helpers ─────────────────────────────────────────────────────────────

def _fake_encode_factory():
    """문자열 → 결정론적 가짜 벡터.

    테스트 케이스를 실제 의미 관계를 반영하도록 수동 매핑한다. 이 함수는
    monkeypatch로 normalize._encode를 교체하는 데 쓴다.
    """
    import numpy as np

    # 각 "의미 그룹"에 같은 (거의 같은) 벡터를 할당
    groups = {
        "remote_control": ["Remote Control", "remote control", "Remote controller", "RemoteControl"],
        "voice_recognition": ["음성 인식", "음성인식", "음성인식 기술", "voice recognition"],
        "craig": ["Craig"],
        "greg": ["Greg"],  # Craig과 의도적으로 멀리 둠 — 사람 이름 오인식 오병합 방지
        "laura": ["Laura", "Laura Smith"],  # 같은 사람
        "david": ["David"],
    }

    vectors = {}
    for i, (_, names) in enumerate(groups.items()):
        base = np.zeros(8, dtype=np.float32)
        base[i] = 1.0
        # 그룹 내 변형은 1.0 벡터에 아주 작은 노이즈만
        for j, name in enumerate(names):
            v = base.copy()
            v[(i + 1) % 8] = 0.02 * j  # 미세 차이
            vectors[name] = v

    def fake_encode(text: str):
        text = text.strip()
        if not text:
            return None
        if text in vectors:
            return vectors[text]
        # 알려지지 않은 단어 — 전부 다른 축에 두기
        import hashlib
        h = int(hashlib.md5(text.encode()).hexdigest(), 16)
        v = np.zeros(8, dtype=np.float32)
        v[h % 8] = 0.5
        return v

    return fake_encode


@pytest.fixture
def mock_encode(monkeypatch):
    """_encode를 가짜로 교체. 모델 다운로드 없음."""
    fake = _fake_encode_factory()
    monkeypatch.setattr(normalize, "_encode", fake)
    normalize.clear_cache()
    yield


# ── 1. disable 스위치 ─────────────────────────────────────────────────

def test_disable_returns_none(monkeypatch):
    monkeypatch.setenv("NORMALIZE_DISABLE", "1")
    result = normalize.find_canonical_name(
        "Remote Control", ["Remote controller"], threshold=0.5
    )
    assert result is None


def test_enable_by_default(monkeypatch, mock_encode):
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    result = normalize.find_canonical_name(
        "Remote Control", ["Remote Control"], threshold=0.85
    )
    assert result == "Remote Control"


# ── 2. fast path: 완전 일치 ─────────────────────────────────────────

def test_exact_match_fast_path(monkeypatch, mock_encode):
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    # 완전히 같은 이름이 이미 존재하면 그대로 반환
    result = normalize.find_canonical_name("Laura", ["Andrew", "Laura", "David"])
    assert result == "Laura"


def test_exact_match_with_whitespace(monkeypatch, mock_encode):
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    result = normalize.find_canonical_name("  Laura  ", ["Laura"])
    assert result == "Laura"


# ── 3. empty inputs ────────────────────────────────────────────────

def test_empty_existing_returns_none(monkeypatch, mock_encode):
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    assert normalize.find_canonical_name("Laura", []) is None


def test_empty_candidate_returns_none(monkeypatch, mock_encode):
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    assert normalize.find_canonical_name("", ["Laura"]) is None


# ── 4. 유사 개념 병합 ────────────────────────────────────────────────

def test_similar_topic_merges(monkeypatch, mock_encode):
    """같은 의미 그룹의 표현들은 첫 번째 canonical로 병합돼야."""
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    existing = ["Remote Control"]
    result = normalize.find_canonical_name(
        "remote control", existing, threshold=0.85
    )
    assert result == "Remote Control"


def test_korean_topic_merges(monkeypatch, mock_encode):
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    existing = ["음성 인식"]
    result = normalize.find_canonical_name(
        "음성인식 기술", existing, threshold=0.85
    )
    assert result == "음성 인식"


# ── 5. 다른 개념은 병합하면 안 됨 ─────────────────────────────────────

def test_different_person_names_not_merged(monkeypatch, mock_encode):
    """Craig과 Greg은 다른 사람 — 병합되면 안 됨.

    이 테스트는 실제 사람 이름 오인식이 그래프에 섞이는 걸 방지한다.
    Speaker에 높은 임계값(0.92)을 쓰는 이유.
    """
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    existing = ["Craig"]
    # 임계값 0.92로 Greg은 병합되지 않아야 함
    result = normalize.find_canonical_name("Greg", existing, threshold=0.92)
    assert result is None


def test_unrelated_topics_not_merged(monkeypatch, mock_encode):
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    existing = ["Remote Control"]
    result = normalize.find_canonical_name(
        "음성 인식", existing, threshold=0.85
    )
    assert result is None


# ── 6. 임계값 동작 ──────────────────────────────────────────────────

def test_threshold_controls_strictness(monkeypatch, mock_encode):
    """threshold를 낮추면 더 느슨하게, 높이면 더 엄격하게 매칭."""
    monkeypatch.delenv("NORMALIZE_DISABLE", raising=False)
    existing = ["Remote Control"]

    # 낮은 임계값 — 관련 표현은 매칭
    loose = normalize.find_canonical_name("remote control", existing, threshold=0.5)
    assert loose == "Remote Control"

    # 매우 높은 임계값 — 완전 동일에 가까운 것만
    strict = normalize.find_canonical_name("RemoteControl", existing, threshold=0.999)
    assert strict is None  # 같은 그룹이지만 약간의 노이즈로 0.999는 못 넘김


# ── 7. 실제 모델 (선택적) ───────────────────────────────────────────

@pytest.mark.skipif(
    os.getenv("RUN_REAL_EMBEDDING") != "1",
    reason="실제 모델 다운로드는 RUN_REAL_EMBEDDING=1일 때만",
)
def test_real_model_english_variants():
    """RUN_REAL_EMBEDDING=1일 때만 실행 — 실제 sentence-transformers로 검증."""
    normalize.clear_cache()
    result = normalize.find_canonical_name(
        "remote control", ["Remote Control"], threshold=0.85
    )
    assert result == "Remote Control"


@pytest.mark.skipif(
    os.getenv("RUN_REAL_EMBEDDING") != "1",
    reason="실제 모델 다운로드는 RUN_REAL_EMBEDDING=1일 때만",
)
def test_real_model_korean_variants():
    normalize.clear_cache()
    result = normalize.find_canonical_name(
        "음성인식 기술", ["음성 인식"], threshold=0.85
    )
    assert result == "음성 인식"
