"""Tests for the census layer.

These guard the three promises the demographics module makes, each of which
produces a confident, wrong answer if it silently breaks: shares must be
recomputed from counts rather than averaged, margins of error must survive to
the caller, and a broad race category must never be presented as a specific
national origin.

They run against the built parquet files and skip when those are absent, so a
fresh checkout without a data pull does not report a false failure.
"""
from __future__ import annotations

import pytest

from sim.analysis import demographics as demo

pytestmark = pytest.mark.skipif(
    not demo.available(), reason="census tables not built; run scripts/06_census.py"
)


def test_all_neighborhoods_present():
    """The city has 42 analysis neighbourhoods and the data should carry them."""
    names = demo.neighborhoods()
    assert len(names) == 42
    for expected in ("Tenderloin", "Mission", "Marina", "Chinatown"):
        assert expected in names


def test_shares_are_percentages_not_sums():
    """A share aggregated from tracts must stay within 0-100.

    The first working version of the roll-up summed tract percentages, which
    reported Chinatown as 475 percent Asian. Nothing downstream caught it,
    because a number is a number.
    """
    for place in demo.neighborhoods():
        profile = demo.profile(place)
        if not profile.get("available"):
            continue
        for label, figure in profile.get("shares", {}).items():
            assert 0.0 <= figure["value"] <= 100.0, f"{place} {label} = {figure['value']}"


def test_known_neighbourhood_character():
    """Spot checks against facts about San Francisco that do not move."""
    chinatown = demo.profile("Chinatown")
    assert chinatown["shares"]["Asian, not Hispanic"]["value"] > 60

    tenderloin = demo.profile("Tenderloin")
    assert tenderloin["shares"]["Households with no car"]["value"] > 60
    assert tenderloin["headline"]["Median household income"]["value"] < 80_000

    marina = demo.profile("Marina")
    assert marina["headline"]["Median household income"]["value"] > 150_000


def test_city_population_is_plausible():
    """Tracts should sum to roughly the city's real population."""
    citywide = demo._citywide()
    assert 700_000 < citywide["population"] < 950_000


def test_margins_of_error_survive():
    """Every headline count must carry its margin, or an answer overstates it."""
    profile = demo.profile("Tenderloin")
    population = profile["headline"]["Population"]
    assert "marginOfError" in population
    assert population["marginOfError"] > 0


def test_wide_margins_are_flagged():
    """A figure whose error swamps it must say so rather than read as settled."""
    profile = demo.profile("Tenderloin")
    income = profile["headline"]["Median household income"]
    # the Tenderloin's median income carries a margin over a third of its value
    assert income.get("imprecise") is True
    # and a weighted roll-up of tract medians is not a true median
    assert income.get("approximate") is True


def test_comparison_refuses_gaps_inside_the_error():
    """Two similar places should not be reported as different."""
    result = demo.compare(["Inner Sunset", "Outer Richmond"])
    assert result["available"]
    joined = " ".join(result["verdicts"]).lower()
    assert "margin of error" in joined or "effectively the same" in joined


def test_comparison_reports_a_real_gap():
    """Two genuinely different places should be reported as different."""
    result = demo.compare(["Tenderloin", "Marina"])
    income = next(v for v in result["verdicts"] if "income" in v.lower())
    assert "exceeds" in income
    assert "Marina" in income


def test_ranking_excludes_places_nobody_lives():
    """Parks are analysis neighbourhoods; they must not top a ranking."""
    result = demo.rank("pct_households_no_car", top=5)
    places = [entry["place"] for entry in result["places"]]
    assert "McLaren Park" not in places
    assert "Golden Gate Park" not in places
    assert result["places"][0]["place"] == "Tenderloin"


def test_ranking_holds_out_thin_denominators():
    """A share over a few hundred households must not top a ranking.

    Seacliff's 55 percent cost-burdened renters rests on 229 renter households
    and outranked the Tenderloin's 17,572 at 47 percent, which ranks sampling
    noise above the city's real housing pressure.
    """
    result = demo.rank("pct_renters_cost_burdened", top=6)
    places = [entry["place"] for entry in result["places"]]
    assert "Seacliff" not in places
    assert "Seacliff" in result["excludedAsTooFewToMeasure"]
    # the places that genuinely carry the city's rent burden should surface
    assert {"Bayview Hunters Point", "Chinatown", "Tenderloin"} & set(places)
    # and holding them out must be stated, not silent
    assert result["note"]


def test_community_states_its_limit():
    """Asked about Indian residents, the answer must not pass off 'Asian'."""
    result = demo.community("Indian", "Mission")
    assert "do not break out Indian" in result["limit"]
    assert "Asian, not Hispanic" in result["closestMeasures"]
    # the broad figure is offered, but never under the name that was asked for
    assert "Indian" not in result.get("figures", {})


def test_point_lookup_returns_tracts_and_says_so():
    """A site question gets the tracts around it, with the fuzziness admitted."""
    result = demo.near(-122.4194, 37.7749, 900.0)
    assert result["available"]
    assert result["tractsCounted"] > 0
    assert result["population"] > 0
    assert "approximate" in result["note"]


def test_place_names_resolve_loosely():
    """People type SoMa and FiDi, not the city's official spellings."""
    assert demo.profile("SoMa")["place"] == "South of Market"
    assert demo.profile("the mission")["place"] == "Mission"
    assert demo.profile("FiDi")["place"] == "Financial District/South Beach"


def test_ambiguous_names_resolve_to_the_bigger_place():
    """"Sunset" means Sunset/Parkside, not the smaller Inner Sunset.

    Substring matching resolved it to whichever name came first alphabetically,
    which quietly answered about 27,000 residents when the question was about
    75,000. Nothing in the answer would have looked wrong.
    """
    assert demo.profile("sunset")["place"] == "Sunset/Parkside"
    assert demo.profile("inner sunset")["place"] == "Inner Sunset"
    assert demo.profile("richmond")["place"] == "Outer Richmond"
    assert demo.profile("inner richmond")["place"] == "Inner Richmond"


def test_unknown_place_is_refused_not_guessed():
    """A place the data does not know must not silently become another one."""
    result = demo.profile("Brooklyn")
    assert result["available"] is False
    assert "knownPlaces" in result
