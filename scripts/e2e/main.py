"""Main entry point for the E2E test suite."""

import argparse
import importlib
import os
import sys
import time
import traceback
from pathlib import Path

from e2e.constants import PROVIDER_PRESETS, SECTION_MAP
from e2e.harness import CaptureAdapter, E2EHarness
from e2e.runner import E2ERunner
from e2e.sections import SECTION_REGISTRY


def main():
    parser = argparse.ArgumentParser(description="E2E test suite for social-media-auto-hook")
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Run only a specific section (onboarding, pipeline, narrative, draft, "
        "scheduler, bot, setup, cli, crosscutting, multiprovider, journey, web, queue, hooks) or scenario (A1, B1, etc.)",
    )
    parser.add_argument(
        "--skip-telegram", action="store_true", help="Skip Telegram-dependent sections (F, G, H)"
    )
    parser.add_argument("--verbose", action="store_true", help="Show full LLM outputs inline")
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        choices=list(PROVIDER_PRESETS.keys()),
        help="LLM provider for pipeline tests (claude-cli: $0 subscription, anthropic: ~$3-9 API). "
        "If not specified, you will be prompted to choose.",
    )
    parser.add_argument(
        "--snapshot",
        type=str,
        default=None,
        metavar="NAME",
        help="Load a saved DB snapshot instead of starting fresh. "
        "Skips the expensive LLM setup (sections A/B). "
        "Use --save-snapshots to create snapshots.",
    )
    parser.add_argument(
        "--save-snapshots",
        action="store_true",
        help="Save DB snapshots after key sections complete. "
        "Snapshots are saved to ~/.social-hook/snapshots/ "
        "and can be loaded with --snapshot NAME.",
    )
    args = parser.parse_args()

    # Determine provider
    provider = args.provider
    if provider is None:
        print("\n" + "=" * 60)
        print("  Provider Selection")
        print("  " + "-" * 56)
        print("  Full E2E coverage requires testing all major providers.")
        print("  Choose which provider to use for this run:")
        print()
        for i, (pid, preset) in enumerate(PROVIDER_PRESETS.items(), 1):
            print(f"    {i}. {pid}")
            print(f"       Models: {preset['evaluator']}, {preset['gatekeeper']}")
            print(f"       Cost:   {preset['cost']}")
            print()
        print("  For full coverage, run once with each provider.")
        print("=" * 60)
        while True:
            choice = input("\n  Select provider [1-2]: ").strip()
            if choice == "1":
                provider = "claude-cli"
                break
            elif choice == "2":
                provider = "anthropic"
                break
            else:
                print("  Invalid choice. Enter 1 or 2.")

    # Determine which sections to run
    sections_to_run = set(SECTION_REGISTRY.keys())
    only_scenario = None
    if args.only:
        only = args.only
        if only.lower() in SECTION_MAP:
            sections_to_run = set(SECTION_MAP[only.lower()])
        elif only.upper()[0] in SECTION_REGISTRY:
            # Single scenario (e.g. "C13") — run the section, skip non-matching scenarios
            sections_to_run = {only.upper()[0]}
            if any(c.isdigit() for c in only):
                only_scenario = only.upper()
        else:
            print(f"Unknown section: {args.only}")
            sys.exit(1)

    if args.skip_telegram:
        sections_to_run -= {"F", "G", "H"}

    preset = PROVIDER_PRESETS[provider]
    print("=" * 60)
    print("  E2E Test Suite (LIVE)")
    print("  Repo: social-media-auto-hook")
    print(f"  Provider: {provider} ({preset['cost']})")
    print(f"  Sections: {', '.join(sorted(sections_to_run))}")
    if only_scenario:
        print(f"  Scenario: {only_scenario}")
    if args.snapshot:
        print(f"  Snapshot: {args.snapshot} (loading saved DB state)")
    if args.save_snapshots:
        print("  Save snapshots: enabled")
    print("=" * 60)

    runner = E2ERunner(verbose=args.verbose)
    runner.start_time = time.time()
    runner._only_scenario = only_scenario

    # Resolve real base path before patching HOME
    real_home = os.environ.get("HOME", str(Path.home()))
    real_base = Path(real_home) / ".social-hook"

    harness = E2EHarness(real_base=real_base, provider=provider)
    runner._harness = harness
    adapter = CaptureAdapter()

    # Sections after which we save snapshots (if --save-snapshots)
    _SNAPSHOT_POINTS = {
        "A": "after-onboarding",
        "B": "after-pipeline",
        "C": "after-narrative",
    }

    try:
        print("\n  Setting up isolated environment...")
        harness.setup(snapshot=args.snapshot)
        print(f"  Temp HOME: {harness.fake_home}")
        print(f"  Repo: {harness.repo_path}")
        if args.snapshot:
            print(f"  Loaded snapshot: {args.snapshot} (project_id={harness.project_id})")

        # Run sections in order using the registry
        for letter in "ABCDEFGHIJKLMNQR":
            if letter not in sections_to_run:
                continue
            info = SECTION_REGISTRY[letter]
            print(f"\n--- {letter}. {info['name']} ---")
            mod = importlib.import_module(f"e2e.sections.{info['module']}")
            kwargs = {"adapter": adapter} if info["needs_adapter"] else {}
            mod.run(harness, runner, **kwargs)

            # Save snapshot after key sections
            if args.save_snapshots and letter in _SNAPSHOT_POINTS:
                harness.save_snapshot(_SNAPSHOT_POINTS[letter])

    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    except Exception as e:
        print(f"\n\nFATAL: {e}")
        if args.verbose:
            traceback.print_exc()
    finally:
        harness.teardown()

    runner.print_summary()
    runner.print_review_report()

    sys.exit(0 if runner.all_passed else 1)
