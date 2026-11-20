"""Plot every constellation in the database side-by-side and save the figure.

Loads the database from ``config.yaml``, renders all constellations with
:func:`astragraph.viz.plot_all_constellations`, and writes the result to the
path configured under ``paths.visualization_output`` (default:
``outputs/constellations.png``).
"""

from __future__ import annotations

from pathlib import Path

from astragraph.constellation_db import ConstellationDB, load_config, resolve_path
from astragraph.viz import plot_all_constellations

DEFAULT_CONFIG_PATH = Path("config.yaml")


def main(config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
    """Build the database, plot all constellations, and save the figure."""
    config_path = Path(config_path).expanduser()
    config = load_config(config_path)

    paths = config.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"Config file is missing a 'paths' mapping: {config_path}")

    data_path = resolve_path(paths["constellation_data"], relative_to=config_path)
    output_path = resolve_path(
        paths.get("visualization_output", "outputs/constellations.png"),
        relative_to=config_path,
    )

    db = ConstellationDB(data_path)
    db.load()

    figure, _ = plot_all_constellations(db)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output_path,
        dpi=160,
        facecolor=figure.get_facecolor(),
        bbox_inches="tight",
    )
    print(f"Saved constellation visualization to {output_path}")


if __name__ == "__main__":
    main()
