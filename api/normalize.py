"""
임베딩 기반 이름 정규화 (Speaker / Topic / Entity).

목적
----
LLM 추출 단계에서 Claude가 회차마다 같은 개념을 조금씩 다른 이름으로
뽑아내는 경우(예: "Remote Control" vs "Remote controller", "음성 인식" vs
"음성인식 기술")나 STT 오인식이 만든 표기 차이(예: "Craig" vs "Greg")로
인해 글로벌 MERGE가 실패하는 문제를 해결한다.

동작
----
Speaker / Topic / Entity를 그래프에 MERGE하기 전에, 같은 project_id의
기존 노드 이름 목록과 **다국어 문장 임베딩** 유사도를 비교해서 임계값
이상이면 기존 이름으로 치환한다. 결과적으로 회차 간 병합이 LLM 프롬프트
지시에만 의존하지 않고 서버 레벨에서 한 번 더 보장된다.

모델
----
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- 50+ 언어 지원 (한국어·영어 모두)
- ~120MB, CPU로도 빠름
- 첫 호출 시 HuggingFace에서 자동 다운로드

임계값
------
기본 0.85. 보수적으로 시작해서 실제 병합 결과를 보며 조정한다.
- 0.95 이상: 거의 동일 (대소문자·공백 차이 등)
- 0.85~0.95: 유사 표현 (정규화 대상)
- 0.70~0.85: 관련은 있지만 다른 개념
- 0.70 미만: 무관

임계값을 너무 낮추면 다른 개념이 병합될 수 있고 (예: Craig과 Greg은
사람 이름이라 표기상 유사도가 높을 수 있음 — 이 경우 오히려 0.90 이상
권장), 너무 높이면 "Remote Control" vs "remote control" 정도만
잡힌다. Speaker는 높게, Topic/Entity는 중간으로 운영하는 것을 추천.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

_model = None
_embedding_cache: dict[str, list[float]] = {}


def _disabled() -> bool:
    """NORMALIZE_DISABLE=1이면 전역 비활성 (테스트·디버그용)."""
    return os.getenv("NORMALIZE_DISABLE", "").lower() in ("1", "true", "yes")


def _get_model():
    """sentence-transformers 모델을 lazy load.

    첫 호출 시 120MB 다운로드 + VRAM/RAM 점유가 발생하므로, normalize 기능을
    사용하는 첫 순간까지 import·load를 지연한다. 테스트 환경에서는
    NORMALIZE_DISABLE=1로 완전히 회피 가능.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv(
            "NORMALIZE_MODEL",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        _model = SentenceTransformer(model_name)
    return _model


def _encode(text: str):
    """문자열 하나를 벡터로. 프로세스 내 캐시로 중복 인코딩 방지."""
    text = text.strip()
    if not text:
        return None
    if text in _embedding_cache:
        import numpy as np
        return np.array(_embedding_cache[text])

    model = _get_model()
    vec = model.encode(text, convert_to_numpy=True, show_progress_bar=False)
    _embedding_cache[text] = vec.tolist()
    return vec


def _cosine(a, b) -> float:
    import numpy as np
    denom = (float(np.linalg.norm(a)) * float(np.linalg.norm(b))) or 1e-12
    return float(np.dot(a, b) / denom)


def find_canonical_name(
    candidate: str,
    existing: list[str],
    threshold: float = 0.85,
) -> Optional[str]:
    """candidate와 가장 유사한 기존 이름을 찾아 반환.

    Parameters
    ----------
    candidate : str
        정규화할 새 이름
    existing : list[str]
        같은 project_id에서 이미 등록된 canonical 이름 목록
    threshold : float, default 0.85
        코사인 유사도 임계값. 이 값 이상이면 매칭으로 간주.

    Returns
    -------
    Optional[str]
        매칭된 canonical 이름. 없으면 None (새 이름 그대로 사용).

    Notes
    -----
    - candidate가 existing에 완전 동일하게 있으면 임베딩 없이 반환 (fast path).
    - existing이 비어 있으면 None 반환.
    - NORMALIZE_DISABLE=1이면 항상 None (기능 비활성).
    - 임베딩 실패 시 (빈 문자열 등) None.
    """
    if _disabled():
        return None

    candidate = candidate.strip()
    if not candidate or not existing:
        return None

    # Fast path: 완전 일치
    for name in existing:
        if name.strip() == candidate:
            return name

    # 임베딩 비교
    try:
        cand_vec = _encode(candidate)
        if cand_vec is None:
            return None

        best_name: Optional[str] = None
        best_sim: float = -1.0
        for name in existing:
            name_vec = _encode(name)
            if name_vec is None:
                continue
            sim = _cosine(cand_vec, name_vec)
            if sim > best_sim:
                best_sim = sim
                best_name = name

        if best_name is not None and best_sim >= threshold:
            return best_name
        return None
    except Exception:
        # 모델 로드 실패 등은 조용히 비활성화 — 기존 동작(prompt-based
        # 정규화)로 fallback. 로그만 남긴다.
        import traceback
        traceback.print_exc()
        return None


def clear_cache() -> None:
    """임베딩 캐시 초기화 (테스트용)."""
    _embedding_cache.clear()
