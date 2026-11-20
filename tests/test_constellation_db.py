"""Tests for the constellation graph database."""

from __future__ import annotations

import networkx as nx
import pytest

from astragraph.constellation_db import ConstellationDB

EXPECTED_CONSTELLATIONS = [
    "Cassiopeia",
    "Cygnus",
    "Leo",
    "Lyra",
    "Orion",
    "Scorpius",
    "Ursa Major",
    "Ursa Minor",
]


@pytest.fixture
def db() -> ConstellationDB:
    database = ConstellationDB.from_config("config.yaml")
    database.load()
    return database


def test_all_constellations_load(db: ConstellationDB) -> None:
    """All 8 major constellations load successfully."""
    names = db.list_constellations()
    assert len(names) == 8
    for name in EXPECTED_CONSTELLATIONS:
        assert name in names


def test_each_constellation_is_connected(db: ConstellationDB) -> None:
    """Each constellation loads as a connected graph."""
    for name in db.list_constellations():
        graph = db.get_constellation(name)
        assert isinstance(graph, nx.Graph)
        assert nx.is_connected(graph), f"{name} is not connected"


def test_node_attributes_exist_and_valid(db: ConstellationDB) -> None:
    """Node attributes (ra, dec, magnitude) exist and are valid."""
    for name in db.list_constellations():
        graph = db.get_constellation(name)
        assert graph.number_of_nodes() >= 5
        for node in graph.nodes:
            attrs = graph.nodes[node]
            assert "name" in attrs, f"{name}: node {node} missing 'name'"
            assert "ra" in attrs, f"{name}: node {node} missing 'ra'"
            assert "dec" in attrs, f"{name}: node {node} missing 'dec'"
            assert "magnitude" in attrs, f"{name}: node {node} missing 'magnitude'"
            assert 0.0 <= attrs["ra"] < 360.0, f"{name}: {node} ra out of range"
            assert -90.0 <= attrs["dec"] <= 90.0, f"{name}: {node} dec out of range"
            assert isinstance(attrs["magnitude"], (int, float))


def test_edges_are_bidirectional(db: ConstellationDB) -> None:
    """Edges are bidirectional (undirected graph)."""
    for name in db.list_constellations():
        graph = db.get_constellation(name)
        assert graph.is_directed() is False
        for u, v in graph.edges:
            assert graph.has_edge(v, u), f"{name}: edge {u}-{v} not bidirectional"


def test_get_constellation_returns_graph(db: ConstellationDB) -> None:
    """get_constellation returns a NetworkX graph with stars and lines."""
    graph = db.get_constellation("Orion")
    assert isinstance(graph, nx.Graph)
    assert graph.number_of_nodes() >= 5
    assert graph.number_of_edges() >= 1


def test_get_star_returns_correct_data(db: ConstellationDB) -> None:
    """get_star() returns correct ra, dec, magnitude for a known star."""
    star = db.get_star("Betelgeuse")
    assert star["name"] == "Betelgeuse"
    assert 88.0 < star["ra"] < 90.0, star
    assert 7.0 < star["dec"] < 8.0, star
    assert 0.0 < star["magnitude"] < 1.0, star

    sirius_like = db.get_star("Vega")
    assert sirius_like["name"] == "Vega"
    assert 279.0 < sirius_like["ra"] < 280.0, sirius_like
    assert 38.0 < sirius_like["dec"] < 39.0, sirius_like

    with pytest.raises(KeyError):
        db.get_star("Not A Star")
