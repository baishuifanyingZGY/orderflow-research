"""Portable source launcher, including Python runtimes that ignore .pth files."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from orderflow.cli import main

if __name__ == "__main__":
    main()
