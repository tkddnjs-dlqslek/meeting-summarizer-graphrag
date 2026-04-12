"""
edinburghcstr/ami 데이터셋에서 ES2002a~d 4회차 트랜스크립트 추출.

전략:
  - streaming 모드로 데이터셋 순회 (오디오는 로드하지 않음)
  - 필요한 meeting_id만 필터
  - begin_time 순으로 정렬 후 같은 speaker 연속 발화는 합침
  - speaker_id는 AMI 내부 해시(MEE068 등)라 A/B/C/D로 재레이블링
  - 결과: tests/ami_{meeting_id}.txt

폴백: ES2002a~d를 못 찾으면 발견된 모든 ES 시리즈 4회차 팀을 보고.
"""

import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from datasets import load_dataset

TARGET = {"ES2002a", "ES2002b", "ES2002c", "ES2002d"}
OUT_DIR = Path(__file__).parent

# oversight: ihm(individual headset mic)의 text는 완벽하지 않을 수 있음 —
# edinburghcstr/ami는 ASR용으로 normalized 처리된 텍스트. 의미 분석엔 충분.
CONFIG = "ihm"

# ES2002 시리즈 speaker_id → 실명 매핑.
# 근거: ES2002a (kick-off) transcript의 자기소개 발화에서 확인됨.
#   "I'm Laura and I'm the Project Manager"
#   "Hi I'm David and I'm supposed to be an Industrial Designer"
#   "And I'm Andrew and I'm our Marketing"
#   "Um I'm Craig and I'm User Interface"
# 이 매핑을 시리즈 4회차 전체에 일관 적용하면 Claude가 회차 간 동일 인물을
# 자동으로 병합할 수 있다 (Speaker 글로벌 MERGE의 트리거).
SPEAKER_NAMES = {
    "FEE005": "Laura",   # Project Manager (verified at 67.55s in ES2002a)
    "MEE006": "David",   # Industrial Designer (77.44s)
    "MEE007": "Craig",   # User Interface (85.99s)
    "MEE008": "Andrew",  # Marketing (82.08s)
}


def collect_segments():
    """모든 split을 스트리밍으로 순회하면서 ES* scenario meeting을 수집."""
    all_segments = defaultdict(list)  # meeting_id -> [(begin_time, speaker_id, text), ...]
    meeting_ids_seen = set()
    total_rows = 0

    for split in ["test", "validation", "train"]:
        print(f"[scan] split={split} ...", flush=True)
        try:
            ds = load_dataset("edinburghcstr/ami", CONFIG, split=split, streaming=True)
            # 오디오 컬럼을 제외해서 torchcodec 디코딩을 피한다 (텍스트 메타만 필요)
            ds = ds.select_columns(["meeting_id", "speaker_id", "text", "begin_time"])
        except Exception as e:
            print(f"  failed to load: {e}")
            continue

        for row in ds:
            total_rows += 1
            mid = row.get("meeting_id")
            if mid is None:
                continue
            meeting_ids_seen.add(mid)

            if mid in TARGET:
                all_segments[mid].append(
                    (
                        float(row.get("begin_time", 0.0)),
                        row.get("speaker_id", "?"),
                        (row.get("text", "") or "").strip(),
                    )
                )

            if total_rows % 20000 == 0:
                found = sum(len(v) for v in all_segments.values())
                print(f"  processed {total_rows} rows, {len(meeting_ids_seen)} unique meetings, {found} target segs", flush=True)

        # 이미 4개 meeting 모두 꽤 수집됐으면 조기 종료
        if len(all_segments) == len(TARGET) and all(len(v) >= 50 for v in all_segments.values()):
            print(f"  all targets collected in split={split}, stopping scan")
            break

    return all_segments, meeting_ids_seen


def write_transcript(meeting_id: str, segments: list):
    """seg 리스트를 정렬 → speaker_id를 시리즈 전체 일관 매핑으로 치환 → 저장."""
    segments.sort(key=lambda x: x[0])

    # speaker 이름 결정: 하드코딩 매핑이 있으면 실명, 없으면 speaker_id 원본 사용.
    # 실명이 4회차 전체에 동일하게 적용되어 글로벌 MERGE가 자동으로 일어남.
    def name_of(spk_id: str) -> str:
        return SPEAKER_NAMES.get(spk_id, spk_id)

    unique_speakers = sorted({name_of(s) for _, s, _ in segments})

    lines = [
        f"Meeting ID: {meeting_id}",
        f"Source: edinburghcstr/ami ({CONFIG})",
        f"Speakers: {', '.join(unique_speakers)} ({len(unique_speakers)} participants)",
        "",
    ]

    # 같은 speaker 연속 발화는 합침
    current_spk = None
    current_texts = []
    for _, spk, text in segments:
        if not text:
            continue
        name = name_of(spk)
        if name != current_spk:
            if current_texts:
                lines.append(f"{current_spk}: {' '.join(current_texts)}")
            current_spk = name
            current_texts = [text]
        else:
            current_texts.append(text)
    if current_texts:
        lines.append(f"{current_spk}: {' '.join(current_texts)}")

    out = OUT_DIR / f"ami_{meeting_id}.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out, len(segments), len(unique_speakers)


def main():
    print(f"Target meetings: {sorted(TARGET)}")
    print(f"Config: {CONFIG}\n")

    segments_by_meeting, meeting_ids_seen = collect_segments()

    print(f"\n=== 수집 결과 ===")
    print(f"전체 unique meeting_id 개수: {len(meeting_ids_seen)}")

    # 타겟 결과
    found = set(segments_by_meeting.keys())
    missing = TARGET - found
    print(f"타겟 발견: {sorted(found)}")
    if missing:
        print(f"타겟 누락: {sorted(missing)}")

    # ES 시리즈 대안 확인
    es_mids = sorted(m for m in meeting_ids_seen if m.startswith("ES"))
    if es_mids:
        print(f"\n데이터셋에 존재하는 ES 시리즈 (앞 20개): {es_mids[:20]}")

    # 저장
    print(f"\n=== 트랜스크립트 저장 ===")
    for mid in sorted(segments_by_meeting.keys()):
        out, n_segs, n_spk = write_transcript(mid, segments_by_meeting[mid])
        print(f"  {out.name}: {n_segs} utterances, {n_spk} speakers")

    if missing:
        print(f"\n[!] 누락된 meeting이 있습니다. 대안 팀을 사용하세요.")
        sys.exit(1)
    print("\n[OK] 4회차 전부 추출 완료")


if __name__ == "__main__":
    main()
