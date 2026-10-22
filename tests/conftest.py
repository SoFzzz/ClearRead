"""Shared pytest hooks."""

import gc
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def collect_widget_cycles_on_the_main_thread(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """Free window trees from the GUI thread.

    Window trees sit in reference cycles. If the automatic garbage collector frees them while
    a worker thread allocates, Qt destroys widgets off the GUI thread and the run dies with an
    access violation. Collecting here, after qtbot has torn down, makes it deterministic.
    """
    yield
    if "qtbot" in request.fixturenames:
        gc.collect()
