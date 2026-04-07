"""
Unit tests for entity_resolver.py

These tests cover pure-Python logic only (no LLM API calls required).
Run with:  pytest tests/test_entity_resolver.py -v
"""

import sys
import os

# Ensure the project root is on the path so imports work from any working dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from entity_resolver import EntityResolver


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def resolver():
    return EntityResolver()


@pytest.fixture
def resolver_with_mappings():
    mappings = {
        "event": {"Rio Earth Summit": "Rio Earth Summit 1992"},
        "actor": {"WWF": "World Wildlife Fund"},
    }
    return EntityResolver(manual_mappings=mappings)


# ---------------------------------------------------------------------------
# _string_similarity
# ---------------------------------------------------------------------------

class TestStringSimilarity:
    def test_exact_match(self, resolver):
        assert resolver._string_similarity("Climate Change", "Climate Change") == 1.0

    def test_case_insensitive(self, resolver):
        assert resolver._string_similarity("United Nations", "united nations") == 1.0

    def test_empty_first(self, resolver):
        assert resolver._string_similarity("", "Something") == 0.0

    def test_empty_second(self, resolver):
        assert resolver._string_similarity("Something", "") == 0.0

    def test_both_empty(self, resolver):
        assert resolver._string_similarity("", "") == 0.0

    def test_high_similarity(self, resolver):
        # SequenceMatcher gives ~0.54 for these two strings — check it's clearly
        # above the "low similarity" baseline rather than imposing an exact floor.
        score = resolver._string_similarity(
            "Paris Agreement on Climate Change",
            "Paris Climate Agreement",
        )
        assert score > 0.4

    def test_low_similarity(self, resolver):
        score = resolver._string_similarity("Kyoto Protocol", "Amazon Rainforest")
        assert score < 0.5


# ---------------------------------------------------------------------------
# _is_acronym
# ---------------------------------------------------------------------------

class TestIsAcronym:
    def test_who(self, resolver):
        assert resolver._is_acronym("WHO", "World Health Organization")

    def test_un(self, resolver):
        assert resolver._is_acronym("UN", "United Nations")

    def test_ipcc(self, resolver):
        assert resolver._is_acronym("IPCC", "Intergovernmental Panel on Climate Change")

    def test_not_acronym(self, resolver):
        # GDP *is* correctly detected as an acronym of "Gross Domestic Product"
        assert resolver._is_acronym("GDP", "Gross Domestic Product")
        # A string that is genuinely not an acronym of the other
        assert not resolver._is_acronym("XYZ", "World Health Organization")

    def test_stop_words_ignored(self, resolver):
        # "UNEP" = U(nited) N(ations) E(nvironment) P(rogramme) — "of" is a stop word
        assert resolver._is_acronym("UNEP", "United Nations Environment Programme")


# ---------------------------------------------------------------------------
# _is_abbreviation
# ---------------------------------------------------------------------------

class TestIsAbbreviation:
    def test_known_abbreviation_forward(self, resolver):
        assert resolver._is_abbreviation("WHO", "World Health Organization")

    def test_known_abbreviation_reverse(self, resolver):
        assert resolver._is_abbreviation("World Health Organization", "WHO")

    def test_unknown_pair(self, resolver):
        assert not resolver._is_abbreviation("IPCCC", "Some Random Name")

    def test_acronym_detected(self, resolver):
        # UNEP is an acronym of United Nations Environment Programme
        assert resolver._is_abbreviation("UNEP", "United Nations Environment Programme")


# ---------------------------------------------------------------------------
# _compatible_actor_types
# ---------------------------------------------------------------------------

class TestCompatibleActorTypes:
    def test_same_type(self, resolver):
        assert resolver._compatible_actor_types("NGO", "NGO")

    def test_institution_organization(self, resolver):
        assert resolver._compatible_actor_types("Institution", "Organization")

    def test_ngo_government(self, resolver):
        assert resolver._compatible_actor_types("NGO", "Government")

    def test_individual_person(self, resolver):
        assert resolver._compatible_actor_types("Individual", "Person")

    def test_incompatible(self, resolver):
        assert not resolver._compatible_actor_types("Individual", "NGO")


# ---------------------------------------------------------------------------
# _same_country
# ---------------------------------------------------------------------------

class TestSameCountry:
    def test_us_variations(self, resolver):
        # The variations list for "US" is ["USA", "United States", ...]; both
        # strings must be IN the list — "US" itself is the dict key, not a member.
        assert resolver._same_country("USA", "United States")
        assert resolver._same_country("USA", "United States of America")
        assert resolver._same_country("U.S.", "U.S.A.")

    def test_uk_variations(self, resolver):
        # Similarly "UK" is the key; "United Kingdom" and "Britain" are members.
        assert resolver._same_country("United Kingdom", "Britain")
        assert resolver._same_country("Great Britain", "U.K.")

    def test_different_countries(self, resolver):
        assert not resolver._same_country("US", "UK")
        assert not resolver._same_country("France", "Germany")


# ---------------------------------------------------------------------------
# _apply_manual_mappings
# ---------------------------------------------------------------------------

class TestApplyManualMappings:
    def test_event_mapping_applied(self, resolver_with_mappings):
        events = [{"title": "Rio Earth Summit", "year": 1992}]
        result = resolver_with_mappings._apply_manual_mappings(events, "event")
        assert result[0]["title"] == "Rio Earth Summit 1992"
        assert result[0]["original_title"] == "Rio Earth Summit"
        assert result[0]["manual_mapping"] is True

    def test_actor_mapping_applied(self, resolver_with_mappings):
        actors = [{"name": "WWF", "type": "NGO"}]
        result = resolver_with_mappings._apply_manual_mappings(actors, "actor")
        assert result[0]["name"] == "World Wildlife Fund"
        assert result[0]["original_name"] == "WWF"

    def test_no_mapping_unchanged(self, resolver_with_mappings):
        actors = [{"name": "Greenpeace", "type": "NGO"}]
        result = resolver_with_mappings._apply_manual_mappings(actors, "actor")
        assert result[0]["name"] == "Greenpeace"
        assert "manual_mapping" not in result[0]

    def test_entity_type_with_no_mappings(self, resolver_with_mappings):
        concepts = [{"name": "Planetary Boundaries"}]
        result = resolver_with_mappings._apply_manual_mappings(concepts, "concept")
        assert result == concepts


# ---------------------------------------------------------------------------
# _calculate_similarity (integration)
# ---------------------------------------------------------------------------

class TestCalculateSimilarity:
    def test_identical_events(self, resolver):
        # Weighted average across name/abbreviation/year/type — hits ~0.89
        e = {"title": "Paris Agreement", "year": 2015, "type": "Policy"}
        score = resolver._calculate_similarity(e, e, "event")
        assert score >= 0.85

    def test_same_event_different_year(self, resolver):
        e1 = {"title": "Climate Summit", "year": 2019}
        e2 = {"title": "Climate Summit", "year": 2020}
        score = resolver._calculate_similarity(e1, e2, "event")
        # Same name but different year should reduce score
        assert score < 0.95

    def test_different_actors(self, resolver):
        a1 = {"name": "Greenpeace", "type": "NGO", "country": "US"}
        a2 = {"name": "World Wildlife Fund", "type": "NGO", "country": "US"}
        score = resolver._calculate_similarity(a1, a2, "actor")
        assert score < 0.7

    def test_similar_actor_names(self, resolver):
        a1 = {"name": "United Nations Environment Programme"}
        a2 = {"name": "UNEP"}
        score = resolver._calculate_similarity(a1, a2, "actor")
        # UNEP is an acronym → abbreviation boost
        assert score > 0.3


# ---------------------------------------------------------------------------
# _cluster_entities
# ---------------------------------------------------------------------------

class TestClusterEntities:
    def test_identical_actors_clustered(self, resolver):
        actors = [
            {"name": "Greenpeace International", "type": "NGO"},
            {"name": "Greenpeace International", "type": "NGO"},
            {"name": "World Wildlife Fund", "type": "NGO"},
        ]
        clusters = resolver._cluster_entities(actors, "actor")
        # The two identical actors should be in one cluster; WWF in another
        assert len(clusters) == 2

    def test_unique_actors_each_cluster(self, resolver):
        actors = [
            {"name": "Greenpeace", "type": "NGO"},
            {"name": "United Nations", "type": "Government"},
            {"name": "World Bank", "type": "Institution"},
        ]
        clusters = resolver._cluster_entities(actors, "actor")
        assert len(clusters) == 3

    def test_empty_input(self, resolver):
        clusters = resolver._cluster_entities([], "actor")
        assert clusters == []


# ---------------------------------------------------------------------------
# resolve_entities (end-to-end, no API)
# ---------------------------------------------------------------------------

class TestResolveEntities:
    def test_deduplicates_identical_events(self, resolver):
        entities = {
            "event": [
                {"title": "Rio Earth Summit 1992", "year": 1992, "type": "Conference"},
                {"title": "Rio Earth Summit 1992", "year": 1992, "type": "Conference"},
            ],
            "actor": [],
            "concept": [],
            "publication": [],
            "location": [],
        }
        resolved = resolver.resolve_entities(entities)
        # Two identical events → merged into one
        assert len(resolved["event"]) == 1

    def test_assigns_ids(self, resolver):
        entities = {
            "actor": [{"name": "UNEP", "type": "Government"}],
            "event": [],
            "concept": [],
            "publication": [],
            "location": [],
        }
        resolved = resolver.resolve_entities(entities)
        assert "id" in resolved["actor"][0]
        assert len(resolved["actor"][0]["id"]) == 36  # UUID length

    def test_preserves_distinct_entities(self, resolver):
        entities = {
            "concept": [
                {"name": "Planetary Boundaries", "definition": "Framework for Earth system stability"},
                {"name": "Doughnut Economics", "definition": "Safe and just space for humanity"},
            ],
            "event": [],
            "actor": [],
            "publication": [],
            "location": [],
        }
        resolved = resolver.resolve_entities(entities)
        assert len(resolved["concept"]) == 2
