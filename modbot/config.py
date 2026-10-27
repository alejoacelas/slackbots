import tomllib
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "channels.toml"


def load_channels() -> dict[str, dict]:
    with CONFIG.open("rb") as f:
        return {c["id"]: c for c in tomllib.load(f)["channel"]}
