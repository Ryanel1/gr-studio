"""Sequential photo operations keep batch memory bounded to one image."""


def process_photos(items, operation, progress, cancelled):
    results, errors = [], []
    for index, (path, settings) in enumerate(items):
        if cancelled.is_set():
            break
        progress((index, len(items), path))
        try:
            results.append((path, operation(path, settings)))
        except Exception as exc:
            errors.append((path, str(exc)))
        progress((index + 1, len(items), path))
    return results, errors, cancelled.is_set()
