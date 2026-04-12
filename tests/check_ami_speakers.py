"""ES2002 시리즈의 speaker_id가 회차 간 일관되는지 확인."""

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

def main():
    per_meeting = defaultdict(set)
    first_appearance_order = defaultdict(list)

    for split in ["train", "validation", "test"]:
        try:
            ds = load_dataset("edinburghcstr/ami", "ihm", split=split, streaming=True)
            ds = ds.select_columns(["meeting_id", "speaker_id", "begin_time"])
        except Exception as e:
            print(f"skip {split}: {e}")
            continue

        for row in ds:
            mid = row["meeting_id"]
            if mid not in TARGET:
                continue
            spk = row["speaker_id"]
            if spk not in per_meeting[mid]:
                per_meeting[mid].add(spk)
                first_appearance_order[mid].append((row["begin_time"], spk))

        if len(per_meeting) == len(TARGET):
            break

    print("=== Speaker IDs per meeting ===")
    all_spks = set()
    for mid in sorted(per_meeting):
        spks = sorted(per_meeting[mid])
        all_spks.update(spks)
        print(f"  {mid}: {spks}")

    print(f"\n=== Union across all 4 meetings ===")
    print(f"  {sorted(all_spks)}")
    print(f"  count = {len(all_spks)}")

    print(f"\n=== Per-meeting intersection ===")
    sets = [per_meeting[m] for m in sorted(per_meeting)]
    common = set.intersection(*sets) if sets else set()
    print(f"  speakers present in ALL 4 meetings: {sorted(common)}")
    print(f"  count = {len(common)}")

    print(f"\n=== First-appearance order per meeting ===")
    for mid in sorted(first_appearance_order):
        ordered = [spk for _, spk in sorted(first_appearance_order[mid])[:6]]
        print(f"  {mid}: {ordered}")


if __name__ == "__main__":
    main()
