"""How to start ClearRead again after the interface language changes."""

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class RelaunchCommand:
    program: str
    arguments: list[str]


def build_relaunch_command(
    frozen: bool, executable: str, argv: list[str]
) -> RelaunchCommand:
    """Command that starts the app the same way it was started now.

    A PyInstaller build is its own executable; from source it is the interpreter
    running the package.
    """
    if frozen:
        return RelaunchCommand(executable, argv[1:])
    return RelaunchCommand(executable, ["-m", "clearread", *argv[1:]])


def current_relaunch_command() -> RelaunchCommand:
    return build_relaunch_command(
        bool(getattr(sys, "frozen", False)), sys.executable, sys.argv
    )
