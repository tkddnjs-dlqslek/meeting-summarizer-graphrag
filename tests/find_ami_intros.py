"""ES2002a에서 각 자기소개 발화의 실제 speaker_id를 찾는다."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from datasets import load_dataset

TARGETS = ["I'M LAURA", "I'M DAVID", "I'M ANDREW", "I'M CRAIG"]

def main():
    ds = load_dataset("edinburghcstr/ami", "ihm", split="train", streaming=True)
    ds = ds.select_columns(["meeting_id", "speaker_id", "text", "begin_time"])

    hits = []
    for row in ds:
        if row["meeting_id"] != "ES2002a":
            continue
        t = (row["text"] or "").upper()
        for target in TARGETS:
            if target in t:
                hits.append((row["begin_time"], row["speaker_id"], row["text"]))

    hits.sort()
    print(f"Found {len(hits)} self-introduction utterances:\n")
    for begin, spk, text in hits:
        print(f"[{begin:7.2f}s] {spk}:")
        print(f"    {text[:150]}")
        print()


if __name__ == "__main__":
    main()
