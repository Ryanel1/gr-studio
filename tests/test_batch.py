from threading import Event
from gr_studio.batch import process_photos


def test_stop_after_current_photo_preserves_completed_results():
    stop = Event()
    updates = []

    def operation(path, settings):
        stop.set()
        return path.upper()

    results, errors, cancelled = process_photos(
        [("a", None), ("b", None)], operation, updates.append, stop
    )
    assert results == [("a", "A")]
    assert not errors and cancelled
    assert updates[-1] == (1, 2, "a")
