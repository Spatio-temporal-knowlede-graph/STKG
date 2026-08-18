#!/usr/bin/env python3
"""
Expansion of spatio-temporal information module에서는 다음과 같은 노이즈를 정의한다.

- Temporal noise
    - 시간 형식이 ISO8601 규격(YYYY-MM-DDTHH:mm:ssZ)을 따르지 않는 경우
    - 시간 정보가 존재하지 않는 경우
    - 존재하지 않는 시간인 경우
    - 시간 해상도가 서로 다른 경우
- Spatial noise
    - 좌표가 없는 경우
    - 위경도 범위를 벗어나는 경우
    - 좌표 정밀도가 부족한 경우 (소수점 자릿수가 부족한 경우)

------------------------------------------------------------------------------
이 스크립트는 위 7종 노이즈를 GT CSV에 랜덤 주입해 오염본을 생성한다.

입력 : GT_ver1.0.csv
       subject, predicate, object, latitude, longitude, timestamp (6컬럼)
       timestamp 기준 형식 = YYYY-MM-DDTHH:MM:SS.mmmZ
출력 : noise_ver1.0.csv (행 수·행 순서·컬럼 순서 보존, 셀 값만 변형)

노이즈 타입 코드
  [Temporal]
    T1_format      ISO8601 규격 위반 형식 (slash / DMY / epoch / compact / 영문 / 로컬오프셋)
    T2_missing     시간 정보 부재 (빈 값)
    T3_invalid     존재하지 않는 시간 (13월, 32일, 25시, 2월 30일 … ISO 모양은 유지)
    T4_resolution  시간 해상도 상이 (ms 탈락 / 분 / 시 / 날짜만 / us 확장 — ISO 자체는 유효)
  [Spatial]
    S1_missing     좌표 부재 (lat+lon / lat만 / lon만)
    S2_range       위경도 범위 이탈 (자릿수 밀림 ×10, |lat|>90, |lon|>180)
    S3_precision   좌표 정밀도 부족 (소수점 0~3자리로 축소, lat·lon 동시)

주입 규칙
  - 오염 행 비율 = --ratio (기본 0.10, 전체 행 대비)
  - 한 행에는 시간 노이즈 최대 1종 + 공간 노이즈 최대 1종 (--both-share 로 동시 주입 비율 조절)
  - 동일 (input, seed, 파라미터) => 동일 출력 (재현 가능)

사용 예
  python noise_script.py                          # 기본 경로·기본 10%
  python noise_script.py --ratio 0.2 --seed 42
  python noise_script.py --only T2_missing,S1_missing
  python noise_script.py --weights T1_format=3,T4_resolution=1
  python noise_script.py --input GT.csv --output out.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 기본 경로 (STKG/modules/<module>/noise_script.py 기준) ────────────────────
_STKG_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _STKG_ROOT / "data" / "expansion_of_spatio-temporal_information" / "pre-made-input"
DEFAULT_INPUT = _DATA_DIR / "GT_ver1.0.csv"
DEFAULT_OUTPUT = _DATA_DIR / "noise_ver1.0.csv"

REQUIRED_COLUMNS = ["subject", "predicate", "object", "latitude", "longitude", "timestamp"]

TEMPORAL_TYPES = ["T1_format", "T2_missing", "T3_invalid", "T4_resolution"]
SPATIAL_TYPES = ["S1_missing", "S2_range", "S3_precision"]
ALL_TYPES = TEMPORAL_TYPES + SPATIAL_TYPES

# GT의 기준 시간 형식: 2026-08-09T08:53:44.000Z
TS_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?Z$")


# ── 파싱 헬퍼 ────────────────────────────────────────────────────────────────
def parse_ts(value: str) -> datetime | None:
    """GT 형식 타임스탬프를 datetime으로. 형식이 다르면 None."""
    m = TS_RE.match(value.strip())
    if not m:
        return None
    y, mo, d, h, mi, s, frac = m.groups()
    micro = int((frac or "0").ljust(6, "0")[:6])
    try:
        return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), micro, tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_coord(value: str) -> float | None:
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


# ── Temporal 노이즈 ──────────────────────────────────────────────────────────
def t1_format(row: dict, rng: random.Random) -> None:
    """ISO8601(YYYY-MM-DDTHH:mm:ssZ) 규격을 따르지 않는 형식으로 치환."""
    dt = parse_ts(row["timestamp"])
    if dt is None:
        return
    kst = dt.astimezone(timezone(timedelta(hours=9)))
    candidates = [
        dt.strftime("%Y/%m/%d %H:%M:%S"),            # slash + 공백 구분자
        dt.strftime("%d-%m-%Y %H:%M:%S"),            # DMY
        dt.strftime("%m/%d/%Y %I:%M:%S %p"),         # US 12시간제
        str(int(dt.timestamp())),                    # epoch(초)
        str(int(dt.timestamp() * 1000)),             # epoch(밀리초)
        dt.strftime("%Y%m%d%H%M%S"),                 # compact
        dt.strftime("%b %d, %Y %H:%M:%S"),           # 영문 월 표기
        dt.strftime("%Y-%m-%d %H:%M:%S"),            # 'T' 없이 공백
        kst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),     # Z 대신 로컬 오프셋
    ]
    row["timestamp"] = candidates[rng.randrange(len(candidates))]


def t2_missing(row: dict, rng: random.Random) -> None:
    """시간 정보 부재."""
    row["timestamp"] = ""


def t3_invalid(row: dict, rng: random.Random) -> None:
    """ISO 모양은 유지하되 달력상 존재하지 않는 시각으로 치환."""
    dt = parse_ts(row["timestamp"])
    if dt is None:
        return
    mo, d, h, mi, s = f"{dt.month:02d}", f"{dt.day:02d}", f"{dt.hour:02d}", f"{dt.minute:02d}", f"{dt.second:02d}"
    candidates = [
        (      "13",          d,     h,    mi,    s),  # 13월
        (      "00",          d,     h,    mi,    s),  # 0월
        (        mo,       "32",     h,    mi,    s),  # 32일
        (        mo,       "00",     h,    mi,    s),  # 0일
        (      "02",       "30",     h,    mi,    s),  # 2월 30일
        (      "04",       "31",     h,    mi,    s),  # 4월 31일
        (        mo,          d,  "25",    mi,    s),  # 25시
        (        mo,          d,     h,  "61",    s),  # 61분
        (        mo,          d,     h,    mi, "61"),  # 61초
    ]
    mo, d, h, mi, s = candidates[rng.randrange(len(candidates))]
    row["timestamp"] = f"{dt.year:04d}-{mo}-{d}T{h}:{mi}:{s}.000Z"


def t4_resolution(row: dict, rng: random.Random) -> None:
    """형식은 유효하지만 시간 해상도가 기준(ms)과 다른 값으로 치환."""
    dt = parse_ts(row["timestamp"])
    if dt is None:
        return
    candidates = [
        dt.strftime("%Y-%m-%dT%H:%M:%SZ"),               # 초 (ms 탈락)
        dt.strftime("%Y-%m-%dT%H:%MZ"),                  # 분
        dt.strftime("%Y-%m-%dT%HZ"),                     # 시
        dt.strftime("%Y-%m-%d"),                         # 날짜만
        dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",       # 마이크로초
        dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "000Z",  # 나노초 자리까지 확장
    ]
    row["timestamp"] = candidates[rng.randrange(len(candidates))]


# ── Spatial 노이즈 ───────────────────────────────────────────────────────────
def s1_missing(row: dict, rng: random.Random) -> None:
    """좌표 부재 (both / lat만 / lon만)."""
    r = rng.random()
    if r < 0.60:
        row["latitude"] = ""
        row["longitude"] = ""
    elif r < 0.80:
        row["latitude"] = ""
    else:
        row["longitude"] = ""


def s2_range(row: dict, rng: random.Random) -> None:
    """위도 [-90,90] / 경도 [-180,180] 범위를 벗어난 값으로 치환."""
    lat, lon = parse_coord(row["latitude"]), parse_coord(row["longitude"])
    if lat is None or lon is None:
        return
    pick = rng.randrange(6)
    if pick == 0:      # 소수점 위치 밀림 (21.38 -> 213.86)
        row["latitude"] = f"{lat * 10:.8f}"
    elif pick == 1:
        row["latitude"] = f"{rng.uniform(90.000001, 180.0):.8f}"
    elif pick == 2:
        row["latitude"] = f"{-rng.uniform(90.000001, 180.0):.8f}"
    elif pick == 3:    # -157.74 -> -1577.40
        row["longitude"] = f"{lon * 10:.8f}"
    elif pick == 4:
        row["longitude"] = f"{rng.uniform(180.000001, 360.0):.8f}"
    else:
        row["longitude"] = f"{-rng.uniform(180.000001, 360.0):.8f}"


# 소수점 자릿수별 가중치: 0자리(~111km) 는 드물게, 2~3자리(~1km/~100m) 를 흔하게
_PRECISION_CHOICES = [0, 1, 2, 3]
_PRECISION_WEIGHTS = [1, 2, 4, 4]


def s3_precision(row: dict, rng: random.Random) -> None:
    """좌표 정밀도 부족 - 소수점 자릿수를 0~3자리로 축소 (lat·lon 동일 자릿수)."""
    lat, lon = parse_coord(row["latitude"]), parse_coord(row["longitude"])
    if lat is None or lon is None:
        return
    d = rng.choices(_PRECISION_CHOICES, weights=_PRECISION_WEIGHTS, k=1)[0]
    row["latitude"] = f"{lat:.{d}f}"
    row["longitude"] = f"{lon:.{d}f}"


INJECTORS = {
    "T1_format": t1_format,
    "T2_missing": t2_missing,
    "T3_invalid": t3_invalid,
    "T4_resolution": t4_resolution,
    "S1_missing": s1_missing,
    "S2_range": s2_range,
    "S3_precision": s3_precision,
}


# ── 인자 파싱 헬퍼 ───────────────────────────────────────────────────────────
def parse_type_list(spec: str) -> list[str]:
    types = [t.strip() for t in spec.split(",") if t.strip()]
    for t in types:
        if t not in ALL_TYPES:
            raise SystemExit(f"[error] 알 수 없는 노이즈 타입: {t}\n         허용: {', '.join(ALL_TYPES)}")
    return types


def parse_weights(spec: str) -> dict[str, float]:
    weights: dict[str, float] = {}
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise SystemExit(f"[error] --weights 형식 오류: {token} (예: T1_format=3)")
        key, value = token.split("=", 1)
        key = key.strip()
        if key not in ALL_TYPES:
            raise SystemExit(f"[error] 알 수 없는 노이즈 타입: {key}")
        try:
            weights[key] = float(value)
        except ValueError:
            raise SystemExit(f"[error] --weights 가중치는 숫자여야 함: {token}")
        if weights[key] < 0:
            raise SystemExit(f"[error] --weights 가중치는 음수일 수 없음: {token}")
    return weights


def weighted_pick(types: list[str], weights: dict[str, float], rng: random.Random) -> str:
    return rng.choices(types, weights=[weights[t] for t in types], k=1)[0]


# ── 메인 ─────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="GT CSV에 시간·공간 노이즈 7종을 랜덤 주입해 오염본을 생성한다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT, help=f"GT CSV 경로 (기본: {DEFAULT_INPUT})")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"출력 CSV 경로 (기본: {DEFAULT_OUTPUT})")
    p.add_argument("--ratio", type=float, default=0.10, help="전체 행 대비 오염 행 비율 (기본 0.10)")
    p.add_argument("--both-share", type=float, default=0.20,
                   help="오염 행 중 시간+공간 노이즈를 동시에 받는 비율 (기본 0.20)")
    p.add_argument("--only", type=str, default=None,
                   help="사용할 노이즈 타입 제한 (쉼표 구분, 예: T2_missing,S1_missing)")
    p.add_argument("--weights", type=str, default=None,
                   help="타입별 가중치 (기본 균등, 예: T1_format=3,T4_resolution=1)")
    p.add_argument("--seed", type=int, default=20260818, help="난수 시드 (기본 20260818)")
    p.add_argument("--force", action="store_true", help="출력 파일이 이미 있어도 덮어쓴다")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Windows 콘솔(cp949 등)에서 요약 출력이 깨져 죽지 않도록
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    if not 0.0 <= args.ratio <= 1.0:
        raise SystemExit("[error] --ratio 는 0.0 ~ 1.0 범위여야 함")
    if not 0.0 <= args.both_share <= 1.0:
        raise SystemExit("[error] --both-share 는 0.0 ~ 1.0 범위여야 함")
    active = parse_type_list(args.only) if args.only else list(ALL_TYPES)
    weights = {t: 1.0 for t in active}
    if args.weights:
        for k, v in parse_weights(args.weights).items():
            if k in weights:
                weights[k] = v
    temporal = [t for t in active if t in TEMPORAL_TYPES and weights[t] > 0]
    spatial = [t for t in active if t in SPATIAL_TYPES and weights[t] > 0]
    if not temporal and not spatial:
        raise SystemExit("[error] 활성화된 노이즈 타입이 없음")

    if not args.input.exists():
        raise SystemExit(f"[error] 입력 파일 없음: {args.input}")
    if args.output.resolve() == args.input.resolve():
        raise SystemExit("[error] 출력 경로가 입력(GT)과 동일함 - GT를 덮어쓸 수 없음")
    if args.output.exists() and not args.force:
        raise SystemExit(f"[error] 출력 파일이 이미 존재함: {args.output}\n        덮어쓰려면 --force")

    # ── 읽기 (원본 문자열 그대로 보존) ──
    with args.input.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise SystemExit(f"[error] 입력 CSV에 필수 컬럼 없음: {', '.join(missing)}")
        rows = [dict(r) for r in reader]

    n = len(rows)
    if n == 0:
        raise SystemExit("[error] 입력 CSV에 데이터 행이 없음")

    rng = random.Random(args.seed)

    # ── 오염 대상 행 선정 및 시간/공간 배정 ──
    n_noisy = round(n * args.ratio)
    noisy_idx = rng.sample(range(n), n_noisy)
    rng.shuffle(noisy_idx)

    if temporal and spatial:
        n_both = round(n_noisy * args.both_share)
        n_rest = n_noisy - n_both
        n_temporal_only = n_rest // 2
        both_idx = noisy_idx[:n_both]
        temporal_idx = noisy_idx[n_both:n_both + n_temporal_only]
        spatial_idx = noisy_idx[n_both + n_temporal_only:]
    elif temporal:
        both_idx, temporal_idx, spatial_idx = [], noisy_idx, []
    else:
        both_idx, temporal_idx, spatial_idx = [], [], noisy_idx

    # ── 주입 ──
    counts = {t: 0 for t in ALL_TYPES}

    def inject(idx_list: list[int], types: list[str]) -> None:
        for i in idx_list:
            t = weighted_pick(types, weights, rng) if len(types) > 1 else types[0]
            INJECTORS[t](rows[i], rng)
            counts[t] += 1

    inject(temporal_idx + both_idx, temporal)
    inject(spatial_idx + both_idx, spatial)

    # ── 쓰기 (컬럼 순서·개행 LF 유지) ──
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    # ── 요약 ──
    dirty = len(noisy_idx)
    print(f"[input ] {args.input}")
    print(f"[output] {args.output}")
    print(f"[seed  ] {args.seed}")
    print(f"[rows  ] 전체 {n:,} / 오염 {dirty:,} ({100 * dirty / n:.2f}%)"
          f"  | 시간만 {len(temporal_idx):,} / 공간만 {len(spatial_idx):,} / 동시 {len(both_idx):,}")
    print("[types ]")
    for t in ALL_TYPES:
        if counts[t] or t in active:
            print(f"    {t:<14} {counts[t]:>8,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
