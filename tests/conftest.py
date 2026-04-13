"""pytest 설정.

tests/ 디렉토리에는 "통합 실행 스크립트"(run_ami_text.py, verify_*.py 등)와
진짜 단위 테스트(test_*.py)가 섞여 있다. pytest는 기본적으로 test_로 시작하는
파일만 수집하지만, 아래 collect_ignore 리스트로 명시해서 혹시 모를 오염을
방지한다. 통합 스크립트는 직접 `python tests/xxx.py`로 실행한다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가해서 `from api.normalize import ...` 등이
# pytest 컨텍스트에서 동작하도록 한다.
sys.path.insert(0, str(Path(__file__).parent.parent))


collect_ignore_glob = [
    "run_*.py",
    "verify_*.py",
    "fetch_*.py",
    "check_*.py",
    "find_*.py",
    "qa_*.py",
    "phase4_eval.py",
]
