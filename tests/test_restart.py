"""How the app starts itself again after a language change."""

from clearread.core.restart import RelaunchCommand, build_relaunch_command


def test_a_frozen_build_runs_its_own_executable_with_the_same_arguments() -> None:
    command = build_relaunch_command(
        True, "C:/ClearRead/ClearRead.exe", ["ClearRead.exe", "--flag"]
    )
    assert command == RelaunchCommand("C:/ClearRead/ClearRead.exe", ["--flag"])


def test_a_frozen_build_without_arguments_passes_none() -> None:
    command = build_relaunch_command(True, "ClearRead.exe", ["ClearRead.exe"])
    assert command.arguments == []


def test_from_source_the_interpreter_runs_the_package_again() -> None:
    command = build_relaunch_command(
        False, "C:/py/python.exe", ["C:/src/clearread/__main__.py", "--flag"]
    )
    assert command == RelaunchCommand("C:/py/python.exe", ["-m", "clearread", "--flag"])


def test_from_source_without_arguments_only_names_the_module() -> None:
    command = build_relaunch_command(False, "python", ["__main__.py"])
    assert command.arguments == ["-m", "clearread"]
