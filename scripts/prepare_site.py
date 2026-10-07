"""Create reload-safe SPA entry points from the same maintained HTML template."""
from pathlib import Path


def prepare_site(site: Path) -> None:
    html = (site / "index.html").read_bytes()
    for name in ("nrt.html", "retrospective.html"):
        (site / name).write_bytes(html)


if __name__ == "__main__":
    prepare_site(Path(__file__).resolve().parents[1] / "site")
