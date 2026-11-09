"""Layer 3 fork: copy hot state into an isolated working directory per hypothesis.

`fork_session` here is the application-side framing: the SDK / CLI primitive lives at
Layer 2; here we reproduce the *semantics* (shared baseline, isolated scratchpads,
no cross-contamination) using state-file copies.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from .scratchpad import Scratchpad


def fork_for_hypothesis(
    base_hot_state_path: Path,
    hypothesis_id: str,
    forks_root: Path,
) -> Path:
    fork_dir = forks_root / hypothesis_id
    fork_dir.mkdir(parents=True, exist_ok=True)
    target = fork_dir / "hot_state.json"
    shutil.copyfile(base_hot_state_path, target)
    return fork_dir


def merge_findings(scratchpad_paths: Iterable[Path], main_scratchpad: Path) -> None:
    main = Scratchpad(main_scratchpad)
    for path in scratchpad_paths:
        if not path.exists():
            continue
        for entry in Scratchpad(path).read():
            main.append(entry)


# What a fork copies:

# fork_for_hypothesis creates forks_root/<hypothesis_id>.
# It then uses shutil.copyfile to copy the base  hot_state.json  into that folder as a byte-for-byte copy.
# Nothing else is copied. The test  test_fork_for_hypothesis_copies_state_without_mutating_base asserts the fork's
# hot_state.json bytes equal the base bytes.

# Where it writes its own scratchpad:

# fork.py doesn't create a scratchpad itself. The caller opens Scratchpad(fork_dir / "scratchpad.jsonl"),
# so each fork writes to forks_root/<id>/scratchpad.jsonl.
# test_two_forks_produce_independent_scratchpads checks that H1's path is forks/H1/scratchpad.jsonl and H2's is 
# forks/H2/scratchpad.jsonl. It also checks that neither fork's entries show up in the other's file.

# Why the base stays unchanged until merge:

# • Forks only read the base file when copying it. All later writes go to the fork's own copy and its own scratchpad.
# • The base file is untouched: the first test asserts base.read_bytes() == base_bytes, and the second records
# base_bytes_before  as well.
# • The only code that writes back is merge_findings. It reads each fork's scratchpad and appends those entries
# to the main scratchpad. Until it's called, nothing a fork records reaches the main scratchpad.
