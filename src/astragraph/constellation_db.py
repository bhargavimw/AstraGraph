"""Load constellation star data into undirected NetworkX graphs.

The database is intentionally read-only from the caller's perspective: every
constellation is built once at construction time, and each graph contains star
nodes (``name``, ``ra``, ``dec``, ``magnitude``) plus edges for the traditional
stick-figure lines.

Coordinates are J2000.0 decimal degrees. Right ascension is in ``[0, 360)`` and
declination is in ``[-90, 90]``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypedDict, cast

import networkx as nx
import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
_REQUIRED_STAR_FIELDS = ("ra", "dec", "magnitude")


class ConstellationDataError(ValueError):
    """Raised when constellation source data is malformed or inconsistent."""


class StarRecord(TypedDict):
    """A star entry in ``data/constellations.json``."""

    name: str
    ra: float
    dec: float
    magnitude: float


class ConstellationRecord(TypedDict):
    """A constellation entry in ``data/constellations.json``."""

    abbreviation: str
    stars: list[StarRecord]
    lines: list[list[str]]


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Read a YAML configuration file into a dictionary.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file does not contain a YAML mapping.
    """
    path = Path(config_path).expanduser()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Could not read config file: {path}") from exc

    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return cast(dict[str, Any], loaded)


def resolve_path(path_value: str | Path, *, relative_to: str | Path) -> Path:
    """Resolve ``path_value`` relative to the config file's directory.

    Absolute paths are returned unchanged (after ``~`` expansion), while relative
    paths are anchored at the parent directory of ``relative_to``.
    """
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = Path(relative_to).expanduser().resolve().parent / path
    return path.resolve()


def _number(value: object, *, field: str, star_name: str) -> float:
    """Return a finite float or raise a descriptive data error."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConstellationDataError(
            f"{star_name!r} has a non-numeric {field!r}: {value!r}"
        )
    result = float(value)
    if not isfinite(result):
        raise ConstellationDataError(
            f"{star_name!r} has a non-finite {field!r}: {value!r}"
        )
    return result


def build_constellation_graph(record: Mapping[str, Any]) -> nx.Graph:
    """Build one undirected constellation graph from a raw data record.

    This function is pure: it does not mutate ``record`` and returns a new graph.
    Validation ensures every line references a declared star, coordinates are in
    range, and the resulting graph is connected.
    """
    raw_stars = record.get("stars")
    raw_lines = record.get("lines")
    if not isinstance(raw_stars, list) or not raw_stars:
        raise ConstellationDataError("A constellation must contain at least one star")
    if not isinstance(raw_lines, list):
        raise ConstellationDataError("A constellation must contain a 'lines' list")

    graph = nx.Graph()
    for raw_star in raw_stars:
        if not isinstance(raw_star, Mapping):
            raise ConstellationDataError(f"Invalid star record: {raw_star!r}")

        name = raw_star.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConstellationDataError(f"Invalid star name: {name!r}")
        if name in graph:
            raise ConstellationDataError(f"Duplicate star name: {name!r}")

        ra = _number(raw_star.get("ra"), field="ra", star_name=name)
        dec = _number(raw_star.get("dec"), field="dec", star_name=name)
        magnitude = _number(
            raw_star.get("magnitude"), field="magnitude", star_name=name
        )
        if not 0.0 <= ra < 360.0:
            raise ConstellationDataError(
                f"{name!r} has right ascension outside [0, 360): {ra}"
            )
        if not -90.0 <= dec <= 90.0:
            raise ConstellationDataError(
                f"{name!r} has declination outside [-90, 90]: {dec}"
            )

        attributes: dict[str, Any] = {
            "name": name,
            "ra": ra,
            "dec": dec,
            "magnitude": magnitude,
        }
        designation = raw_star.get("designation")
        if isinstance(designation, str) and designation:
            attributes["designation"] = designation
        graph.add_node(name, **attributes)

    for line in raw_lines:
        if not isinstance(line, (list, tuple)) or len(line) != 2:
            raise ConstellationDataError(f"Invalid line record: {line!r}")
        source, target = line
        if not isinstance(source, str) or not isinstance(target, str):
            raise ConstellationDataError(f"Line endpoints must be names: {line!r}")
        if source not in graph or target not in graph:
            missing = source if source not in graph else target
            raise ConstellationDataError(
                f"Line references unknown star {missing!r}: {line!r}"
            )
        if source == target:
            raise ConstellationDataError(f"Line cannot connect a star to itself: {line!r}")
        graph.add_edge(source, target)

    if graph.number_of_nodes() > 1 and not nx.is_connected(graph):
        raise ConstellationDataError("Constellation graph must be connected")
    return graph


def _load_payload(data_path: Path) -> Mapping[str, Any]:
    """Load and type-check the top-level JSON document."""
    try:
        raw = data_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"Could not read constellation data: {data_path}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConstellationDataError(
            f"Invalid JSON in constellation data {data_path}: {exc}"
        ) from exc

    if not isinstance(payload, Mapping):
        raise ConstellationDataError("Constellation data must be a JSON object")
    return payload


class ConstellationDB:
    """An immutable collection of constellation graphs keyed by constellation name.

    Example:
        >>> db = ConstellationDB.from_config("config.yaml")
        >>> orion = db.get("Orion")
        >>> sorted(orion.nodes(data=True))[0][1]["name"]
        'Alnilam'
    """

    def __init__(self, data_path: str | Path) -> None:
        self._data_path = Path(data_path).expanduser().resolve()
        payload = _load_payload(self._data_path)

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ConstellationDataError("'metadata' must be a JSON object")

        raw_constellations = payload.get("constellations")
        if not isinstance(raw_constellations, Mapping) or not raw_constellations:
            raise ConstellationDataError(
                "'constellations' must be a non-empty JSON object"
            )

        built: dict[str, nx.Graph] = {}
        for name, raw_record in raw_constellations.items():
            if not isinstance(name, str) or not name.strip():
                raise ConstellationDataError(f"Invalid constellation name: {name!r}")
            if not isinstance(raw_record, Mapping):
                raise ConstellationDataError(
                    f"Invalid record for constellation {name!r}"
                )

            graph = build_constellation_graph(raw_record)
            abbreviation = raw_record.get("abbreviation")
            graph.graph["name"] = name
            if isinstance(abbreviation, str) and abbreviation:
                graph.graph["abbreviation"] = abbreviation
            built[name] = graph

        self._metadata: Mapping[str, Any] = MappingProxyType(dict(metadata))
        self._constellations: Mapping[str, nx.Graph] = MappingProxyType(built)

    @classmethod
    def from_config(
        cls, config_path: str | Path = DEFAULT_CONFIG_PATH
    ) -> "ConstellationDB":
        """Construct a database using the data path declared in ``config.yaml``."""
        path = Path(config_path).expanduser()
        config = load_config(path)
        paths = config.get("paths")
        if not isinstance(paths, Mapping):
            raise ValueError(f"Config file is missing a 'paths' mapping: {path}")

        data_path = paths.get("constellation_data")
        if not isinstance(data_path, str) or not data_path:
            raise ValueError(
                f"Config file is missing 'paths.constellation_data': {path}"
            )
        return cls(resolve_path(data_path, relative_to=path))

    @property
    def data_path(self) -> Path:
        """Absolute path of the JSON dataset backing this database."""
        return self._data_path

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Dataset metadata (epoch, coordinate frame, units, and so on)."""
        return self._metadata

    @property
    def constellations(self) -> Mapping[str, nx.Graph]:
        """Read-only mapping of constellation names to NetworkX graphs."""
        return self._constellations

    def names(self) -> tuple[str, ...]:
        """Return all constellation names in deterministic alphabetical order."""
        return tuple(sorted(self._constellations))

    def get(self, name: str) -> nx.Graph:
        """Return the graph for ``name``.

        Raises:
            KeyError: If the constellation is not present in the database.
        """
        try:
            return self._constellations[name]
        except KeyError as exc:
            known = ", ".join(self.names())
            raise KeyError(
                f"Unknown constellation {name!r}. Available: {known}"
            ) from exc

    def __getitem__(self, name: str) -> nx.Graph:
        return self.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._constellations

    def __iter__(self) -> Iterator[str]:
        return iter(self._constellations)

    def __len__(self) -> int:
        return len(self._constellations)
