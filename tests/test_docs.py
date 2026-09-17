"""The README quotes numbers from generated reports. Fail if they drift apart."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
RESULTS = (ROOT / "backtests" / "RESULTS.md").read_text(encoding="utf-8")
VERIFICATION = (ROOT / "backtests" / "VERIFICATION.md").read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else None]


def rows(table_section: str) -> list[list[str]]:
    out = []
    for line in table_section.splitlines():
        if line.startswith("|") and not set(line) <= set("|-: "):
            out.append([c.strip() for c in line.strip("|").split("|")])
    return out[1:]   # drop the header


def test_scorecard_sentence_matches():
    m = re.search(r"Gateway matches in (\d+) of the (\d+) events where a relief gateway was used", RESULTS)
    assert m, "RESULTS.md has no scorecard sentence"
    assert m.group(0) in README


def test_scorecard_match_column_matches():
    ours = [r[-1] for r in rows(section(README, "Backtests"))]
    theirs = [r[-1] for r in rows(section(RESULTS, "Scorecard: real events"))]
    assert ours == theirs


def test_scenario_table_numbers_match():
    ours = rows(section(README, "Scenarios"))
    theirs = rows(section(RESULTS, "Scenario summary"))
    assert len(ours) == len(theirs) == 6
    for mine, generated in zip(ours, theirs):
        assert mine[1] == generated[1], f"people at MMI VIII+: README {mine[1]} vs RESULTS {generated[1]}"
        assert mine[4] == generated[4], f"capacity: README {mine[4]} vs RESULTS {generated[4]}"
        assert mine[5] == generated[5], f"share of need: README {mine[5]} vs RESULTS {generated[5]}"
        flagged = int(generated[3])
        assert (flagged == 0) == mine[3].startswith("none"), f"flag count: README {mine[3]!r} vs RESULTS {flagged}"
        if flagged:
            assert mine[3].startswith(str(flagged)), f"flag count: README {mine[3]!r} vs RESULTS {flagged}"


def test_quick_start_example_matches_results():
    for line in ("747-8F x 6 spots, 11,870 ft   inflow 3,160 t/day",):
        assert line in README
    assert "KSFO San Francisco International Airport**, 38 km, MMI VII, inflow 3,160 t/day" in RESULTS


def test_verification_figures_match():
    assert "Total cities compared: 4,155." in VERIFICATION and "4,155 cities" in README
    pooled = re.search(r"\*\*all events pooled\*\* \| ([\d,]+) \| ([\d.]+) \|", VERIFICATION)
    assert pooled and f"off by {pooled.group(2)} intensity units on average across {pooled.group(1)} airports" in README.replace(",", "").replace("1532", "1532")
    legacy = re.search(r"mean difference ([+-][\d.]+), mean absolute [\d.]+, largest ([\d.]+)", VERIFICATION)
    assert legacy and f"mean difference {legacy.group(1).lstrip('+')}, largest {legacy.group(2)}" in README
