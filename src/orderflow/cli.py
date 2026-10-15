from __future__ import annotations
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description="Reproduce the public order-flow study")
    p.add_argument("command", choices=["data", "research", "report", "all"])
    p.add_argument("--config", default="configs/study.json")
    p.add_argument("--root", default=".")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--output", default="results", help="Research output directory; use a fresh directory to reproduce a sealed run")
    args = p.parse_args()
    root = Path(args.root).resolve()
    config = json.loads((root / args.config).read_text())
    if args.command in ("data", "all"):
        from .data import prepare_data
        prepare_data(root, config, args.workers)
    if args.command in ("research", "all"):
        from datetime import date, timedelta
        from .research import run_research
        def days(start, end):
            start, end = date.fromisoformat(start), date.fromisoformat(end)
            return [(start + timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
        after_train = (date.fromisoformat(config["train_end"]) + timedelta(days=1)).isoformat()
        after_validation = (date.fromisoformat(config["validation_end"]) + timedelta(days=1)).isoformat()
        model_config = {"seed": config["seed"], "train_dates": days(config["start_date"], config["train_end"]),
                        "validation_dates": days(after_train, config["validation_end"]),
                        "test_dates": days(after_validation, config["test_end"])}
        run_research(root / "data/processed", root / args.output, model_config)
    if args.command in ("report", "all"):
        from .report import build_report
        build_report(root)


if __name__ == "__main__":
    main()
