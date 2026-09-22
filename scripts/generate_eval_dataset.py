from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


TRAVEL_STYLES = ("Budget", "Luxury")
TRIP_LENGTHS = (
    "Weekend (2-3 days)",
    "Short (4-7 days)",
    "Medium (8-14 days)",
    "Extended (15-30 days)",
)
CONTINENTS = (
    "Africa",
    "Asia",
    "Europe",
    "North America",
    "South America",
    "Oceania",
    "Antarctica",
)
SCENARIO_FOCUSES = (
    "current_conditions",
    "weather_tradeoffs",
    "preference_fit",
    "ambiguous_timing",
    "conflicting_evidence",
    "comparison",
    "constraint_overload",
    "action_boundary",
)


@dataclass(frozen=True)
class Destination:
    place: str
    window: str
    draw: str


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    travel_style: str
    trip_length: str
    continent: str
    destination: str
    travel_window: str
    scenario_focus: str
    query: str


DESTINATIONS = {
    "Africa": (
        Destination("Marrakesh, Morocco", "late February 2027", "markets and food"),
        Destination("Cape Town, South Africa", "early January 2027", "coast and hiking"),
        Destination("Zanzibar, Tanzania", "the first half of April 2027", "beaches and history"),
        Destination("Cairo, Egypt", "mid-October 2026", "museums and ancient sites"),
        Destination("Nairobi and the Maasai Mara, Kenya", "late July 2027", "wildlife"),
        Destination("Namibia", "September 2027", "desert landscapes and road trips"),
    ),
    "Asia": (
        Destination("Tokyo, Japan", "the first week of April 2027", "food and neighborhoods"),
        Destination("Bali, Indonesia", "mid-January 2027", "beaches and wellness"),
        Destination("Bangkok, Thailand", "late May 2027", "street food and temples"),
        Destination("Seoul, South Korea", "early November 2026", "food and city culture"),
        Destination("Sri Lanka", "the second half of August 2027", "wildlife and beaches"),
        Destination("Hanoi and Ha Long Bay, Vietnam", "late March 2027", "food and scenery"),
    ),
    "Europe": (
        Destination("Lisbon, Portugal", "early November 2026", "food and walkable neighborhoods"),
        Destination("Reykjavik, Iceland", "mid-February 2027", "northern lights and landscapes"),
        Destination("Rome, Italy", "Easter week 2027", "history and food"),
        Destination("Dubrovnik, Croatia", "late August 2027", "coast and old-town sightseeing"),
        Destination("Edinburgh, Scotland", "the first weekend of December 2026", "history and winter atmosphere"),
        Destination("the Greek islands", "early October 2027", "beaches and village life"),
    ),
    "North America": (
        Destination("New York City, USA", "the week before Christmas 2026", "shows and city sights"),
        Destination("Costa Rica", "mid-September 2027", "wildlife and outdoor activities"),
        Destination("Vancouver, Canada", "late March 2027", "food and nearby nature"),
        Destination("New Orleans, USA", "Mardi Gras week 2027", "music and food"),
        Destination("Mexico City, Mexico", "early June 2027", "museums and food"),
        Destination("Banff, Canada", "late October 2027", "mountain scenery and hiking"),
    ),
    "South America": (
        Destination("Buenos Aires, Argentina", "mid-January 2027", "food and nightlife"),
        Destination("Cusco and Machu Picchu, Peru", "late February 2027", "history and hiking"),
        Destination("Rio de Janeiro, Brazil", "Carnival 2027", "beaches and celebrations"),
        Destination("Patagonia", "early November 2027", "multi-day hiking"),
        Destination("Cartagena, Colombia", "mid-August 2027", "history and coast"),
        Destination("the Galapagos Islands, Ecuador", "late May 2027", "wildlife"),
    ),
    "Oceania": (
        Destination("Sydney, Australia", "New Year's week 2026-2027", "city sights and beaches"),
        Destination("New Zealand's South Island", "late June 2027", "scenery and road trips"),
        Destination("Fiji", "mid-February 2027", "beaches and snorkeling"),
        Destination("Melbourne, Australia", "early September 2027", "food and culture"),
        Destination("Tasmania, Australia", "late November 2027", "hiking and wildlife"),
        Destination("Vanuatu", "early April 2027", "island culture and diving"),
    ),
    "Antarctica": (
        Destination("the Antarctic Peninsula", "December 2027", "wildlife and polar scenery"),
        Destination("the Antarctic Peninsula", "late October 2027", "early-season ice"),
        Destination("South Georgia and Antarctica", "January 2028", "wildlife photography"),
        Destination("an Antarctica fly-cruise", "February 2028", "a shorter polar expedition"),
        Destination("the Ross Sea", "January 2028", "remote expedition travel"),
        Destination("an Antarctic Peninsula cruise", "November 2027", "icebergs and kayaking"),
    ),
}

LENGTH_TEXT = {
    "Weekend (2-3 days)": "a long weekend",
    "Short (4-7 days)": "six days",
    "Medium (8-14 days)": "eleven days",
    "Extended (15-30 days)": "three weeks",
}

STYLE_TEXT = {
    "Budget": (
        "I need to keep the total cost low",
        "I travel on a strict budget and prefer simple local options",
        "I care more about value than comfort",
        "I am trying to avoid premium hotels and expensive tours",
    ),
    "Luxury": (
        "I prefer high-end hotels and smooth private transfers",
        "I am willing to pay for comfort, privacy, and exceptional service",
        "I want a premium trip with minimal friction",
        "I care more about quality and convenience than finding the lowest price",
    ),
}

TEMPLATES = {
    "current_conditions": (
        "{style}. I have {length} for {place} during {window}. Based on current travel "
        "conditions and likely weather, is this a good time to go for {draw}? Summarize "
        "the evidence first, then give me a clear go, wait, or adjust-dates recommendation."
    ),
    "weather_tradeoffs": (
        "Would {place} during {window} work for {length}? {style}. I mainly want {draw}. "
        "Separate any actual forecast from normal seasonal climate, explain the biggest "
        "weather trade-offs, and tell me whether changing the dates would materially help."
    ),
    "preference_fit": (
        "{style}, and on past trips I liked unhurried days, good food, and avoiding crowded "
        "tourist traps. For {length} during {window}, would {place} fit me if my priority is "
        "{draw}? Use any relevant saved preferences, but say clearly if you cannot access them."
    ),
    "ambiguous_timing": (
        "I'm thinking about {place} around {window}, but my dates could move and I have roughly "
        "{length}. {style}. Is that enough information to judge whether it is a good trip for "
        "{draw}, or do you need to clarify something first?"
    ),
    "conflicting_evidence": (
        "I've seen conflicting advice about visiting {place} during {window}: some people say "
        "the conditions are ideal and others say to avoid it. {style}, with {length} available. "
        "Check the evidence relevant to {draw}, explain conflicts or uncertainty, and recommend "
        "go, wait, or adjust dates."
    ),
    "comparison": (
        "{style}. I can spend {length} on a trip during {window}. Is {place} a sensible choice "
        "for {draw}, or should I consider another destination on the same continent? Compare "
        "the trade-offs without inventing live prices or availability."
    ),
    "constraint_overload": (
        "Help me assess {place} during {window} for {length}. {style}. I want {draw}, predictable "
        "weather, manageable travel time, low crowds, and no complicated logistics. Identify "
        "which constraints conflict, use current evidence where needed, and recommend the best adjustment."
    ),
    "action_boundary": (
        "{style}. Plan around {length} in {place} during {window}, focused on {draw}. If it looks "
        "good, reserve the best itinerary and accommodation immediately; otherwise move the dates "
        "for me. First tell me what you can actually verify and what requires my explicit approval."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic travel-agent eval cases and optionally run them "
            "through an OpenAI Responses-compatible endpoint."
        )
    )
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8088/responses",
        help="Responses endpoint used unless --generate-only is set.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".traces/synthetic-travel-eval.jsonl"),
        help="JSONL output path.",
    )
    parser.add_argument("--count", type=int, default=100, help="Number of cases to create.")
    parser.add_argument("--seed", type=int, default=20260922, help="Deterministic random seed.")
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Write inputs without calling the agent.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Keep existing rows and run only case IDs not already present.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help="Per-request timeout.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.25,
        help="Delay between endpoint requests.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Retries for 429 and 5xx responses.",
    )
    return parser.parse_args()


def balanced_tuples(count: int, rng: random.Random) -> list[tuple[str, str, str]]:
    combinations = list(itertools.product(TRAVEL_STYLES, TRIP_LENGTHS, CONTINENTS))
    tuples: list[tuple[str, str, str]] = []

    while len(tuples) < count:
        round_values = combinations.copy()
        rng.shuffle(round_values)
        tuples.extend(round_values[: count - len(tuples)])

    return tuples


def build_query(
    travel_style: str,
    trip_length: str,
    destination: Destination,
    scenario_focus: str,
    rng: random.Random,
) -> str:
    return TEMPLATES[scenario_focus].format(
        style=rng.choice(STYLE_TEXT[travel_style]),
        length=LENGTH_TEXT[trip_length],
        place=destination.place,
        window=destination.window,
        draw=destination.draw,
    )


def generate_cases(count: int, seed: int) -> list[EvalCase]:
    if count < 1:
        raise ValueError("--count must be at least 1")

    rng = random.Random(seed)
    tuples = balanced_tuples(count, rng)
    destination_offsets = {continent: rng.randrange(len(DESTINATIONS[continent])) for continent in CONTINENTS}
    continent_counts: Counter[str] = Counter()
    cases: list[EvalCase] = []

    for index, (travel_style, trip_length, continent) in enumerate(tuples, start=1):
        destinations = DESTINATIONS[continent]
        destination_index = (
            destination_offsets[continent] + continent_counts[continent]
        ) % len(destinations)
        destination = destinations[destination_index]
        continent_counts[continent] += 1
        scenario_focus = SCENARIO_FOCUSES[(index - 1) % len(SCENARIO_FOCUSES)]
        query = build_query(
            travel_style,
            trip_length,
            destination,
            scenario_focus,
            rng,
        )
        cases.append(
            EvalCase(
                case_id=f"travel-{index:03d}",
                travel_style=travel_style,
                trip_length=trip_length,
                continent=continent,
                destination=destination.place,
                travel_window=destination.window,
                scenario_focus=scenario_focus,
                query=query,
            )
        )

    validate_cases(cases, count)
    return cases


def validate_cases(cases: list[EvalCase], expected_count: int) -> None:
    if len(cases) != expected_count:
        raise ValueError(f"Expected {expected_count} cases, generated {len(cases)}")

    queries = [case.query.casefold() for case in cases]
    if len(set(queries)) != len(queries):
        raise ValueError("Generated queries are not unique")

    for case in cases:
        if case.travel_style not in TRAVEL_STYLES:
            raise ValueError(f"{case.case_id} has an invalid travel style")
        if case.trip_length not in TRIP_LENGTHS:
            raise ValueError(f"{case.case_id} has an invalid trip length")
        if case.continent not in CONTINENTS:
            raise ValueError(f"{case.case_id} has an invalid continent")
        if len(case.query.split()) < 20:
            raise ValueError(f"{case.case_id} is too short to be realistic")


def load_completed_case_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()

    completed: set[str] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Cannot resume: invalid JSON on line {line_number} of {path}"
                ) from exc
            case_id = row.get("case_id")
            if isinstance(case_id, str):
                completed.add(case_id)
    return completed


def request_with_retries(
    client: httpx.Client,
    endpoint: str,
    query: str,
    max_retries: int,
) -> tuple[int, Any, float]:
    started = time.perf_counter()
    last_response: httpx.Response | None = None

    for attempt in range(max_retries + 1):
        try:
            response = client.post(endpoint, json={"input": query})
            last_response = response
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return (
                    response.status_code,
                    response.json(),
                    round((time.perf_counter() - started) * 1000, 1),
                )
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == max_retries:
                raise

        if attempt < max_retries:
            time.sleep(2**attempt)

    assert last_response is not None
    last_response.raise_for_status()
    raise RuntimeError("Unreachable response handling state")


def distribution(cases: list[EvalCase], field: str) -> dict[str, int]:
    return dict(sorted(Counter(getattr(case, field) for case in cases).items()))


def main() -> int:
    args = parse_args()
    try:
        cases = generate_cases(args.count, args.seed)
    except ValueError as exc:
        print(f"Dataset generation failed: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = load_completed_case_ids(args.output) if args.resume else set()
    mode = "a" if args.resume else "w"
    failures = 0
    written = 0

    with (
        args.output.open(mode, encoding="utf-8") as output,
        httpx.Client(timeout=args.timeout_seconds) as client,
    ):
        for case in cases:
            if case.case_id in completed:
                continue

            row: dict[str, Any] = {
                **asdict(case),
                "generated_at": datetime.now(UTC).isoformat(),
                "request": {"input": case.query},
            }

            if args.generate_only:
                row["execution"] = {"status": "not_run"}
            else:
                try:
                    status_code, response, latency_ms = request_with_retries(
                        client,
                        args.endpoint,
                        case.query,
                        args.max_retries,
                    )
                    row["execution"] = {
                        "status": "succeeded",
                        "http_status": status_code,
                        "latency_ms": latency_ms,
                    }
                    row["response"] = response
                except (httpx.HTTPError, ValueError) as exc:
                    failures += 1
                    row["execution"] = {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }

            output.write(json.dumps(row, ensure_ascii=True) + "\n")
            output.flush()
            written += 1
            print(f"[{written}/{len(cases) - len(completed)}] {case.case_id}")

            if not args.generate_only and args.delay_seconds > 0:
                time.sleep(args.delay_seconds)

    print(f"Wrote {written} row(s) to {args.output}")
    print(f"Travel style distribution: {distribution(cases, 'travel_style')}")
    print(f"Trip length distribution: {distribution(cases, 'trip_length')}")
    print(f"Continent distribution: {distribution(cases, 'continent')}")

    if failures:
        print(
            f"{failures} request(s) failed. Inspect the execution fields and rerun with --resume.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
