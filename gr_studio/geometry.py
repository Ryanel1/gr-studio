"""Bounded NumPy line detection and Pillow perspective correction, without OpenCV."""

from itertools import combinations
import math
import numpy as np
from PIL import Image, ImageFilter

IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def checked_matrix(values):
    matrix = np.asarray(values, dtype=float)
    if matrix.size != 9 or not np.isfinite(matrix).all():
        raise ValueError("Invalid perspective correction.")
    matrix = matrix.reshape(3, 3)
    if abs(np.linalg.det(matrix)) < 1e-6 or abs(matrix[2, 2]) < 1e-6:
        raise ValueError("Perspective correction is singular.")
    return matrix / matrix[2, 2]


def project(matrix, points):
    points = np.asarray(points, dtype=float)
    values = np.column_stack((points, np.ones(len(points)))) @ matrix.T
    if np.any(values[:, 2] <= 0.08):
        raise ValueError("Perspective is too extreme. Use less convergent guides.")
    return values[:, :2] / values[:, 2, None]


def _upright(vertical=None, horizontal=None):
    matrix = np.eye(3)
    if vertical is not None:
        a, q = vertical
        matrix[0, 1] = -a
        matrix[1, 0] = a
        matrix[2, 1] = q
    if horizontal is not None:
        b, p = horizontal
        matrix[1, 0] = -b
        if vertical is None:
            matrix[0, 1] = b
        matrix[2, 0] = p
    if vertical is not None and horizontal is not None:
        # Solve the line at infinity against both vanishing directions.
        a, q = vertical
        b, p = horizontal
        matrix[2, :2] = np.linalg.solve([[a, 1], [1, b]], [q, p])
    return checked_matrix(matrix)


def guided_matrix(guides, size):
    """Guides are (vertical|horizontal, (x0,y0), (x1,y1)), in 0..1 image coordinates."""
    width, height = size
    short = min(size)
    families = {}
    for kind in ("vertical", "horizontal"):
        selected = [g for g in guides if g[0] == kind]
        if len(selected) == 1:
            raise ValueError(f"Draw a second {kind} guide, or undo the single guide.")
        if not selected:
            continue
        if len(selected) != 2:
            raise ValueError("Use two guides per direction.")
        lines, centers = [], []
        for _, start, end in selected:
            points = np.asarray([start, end], dtype=float)
            if (
                not np.isfinite(points).all()
                or (points < 0).any()
                or (points > 1).any()
            ):
                raise ValueError("Draw guides inside the photo.")
            points = (points - 0.5) * np.array([width, height]) / short
            delta = points[1] - points[0]
            axis = 1 if kind == "vertical" else 0
            if abs(delta[axis]) < 0.12 or abs(delta[1 - axis]) > abs(delta[axis]) * 0.7:
                raise ValueError(
                    f"Draw a longer, mostly {kind} guide along a straight edge."
                )
            lines.append(np.cross([*points[0], 1], [*points[1], 1]))
            centers.append(points.mean(axis=0)[1 - axis])
        if abs(centers[0] - centers[1]) < 0.08:
            raise ValueError("Place the guides on two different, well-separated edges.")
        vanishing = np.cross(*lines)
        component = vanishing[1 if kind == "vertical" else 0]
        if abs(component) < 1e-8:
            raise ValueError("These guides cannot define a reliable correction.")
        families[kind] = (
            vanishing[0 if kind == "vertical" else 1] / component,
            -vanishing[2] / component,
        )
    if not families:
        raise ValueError("Draw two vertical or two horizontal guides first.")
    matrix = _upright(families.get("vertical"), families.get("horizontal"))
    _crop_geometry(matrix, size)
    return tuple(matrix.ravel())


def _crop_geometry(matrix, size, aspect=1.0):
    """Find a centered, aspect-preserving rectangle wholly inside the transformed photo."""
    width, height = size
    short = min(size)
    corners = np.array(
        [[-width, -height], [width, -height], [width, height], [-width, height]]
    ) / (2 * short)
    project(matrix, corners)
    inverse = np.linalg.inv(matrix)
    bounds = np.array([width, height]) / (2 * short)
    target = bounds * np.array([aspect, 1])
    signs = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])
    low, high = 0.0, 1.0
    for _ in range(32):
        scale = (low + high) / 2
        try:
            source = project(inverse, signs * target * scale)
            fits = np.all(np.abs(source) <= np.maximum(0, bounds - 2 / short))
        except ValueError:
            fits = False
        if fits:
            low = scale
        else:
            high = scale
    if low < 0.25:
        raise ValueError(
            "Correction would crop too much. Reduce the perspective or redraw the guides."
        )
    return max(1, math.floor(width * aspect * low)), max(1, math.floor(height * low))


def transform_geometry(image, settings):
    base = checked_matrix(settings.geometry)
    values = [settings.vertical, settings.horizontal, settings.aspect]
    if not np.isfinite(values).all():
        raise ValueError("Geometry values must be finite.")
    vertical, horizontal, aspect = np.clip(values, -100, 100)
    aspect = 2 ** (aspect / 100)
    manual = np.array(
        [[aspect, 0, 0], [0, 1, 0], [horizontal * 0.006, vertical * 0.006, 1]]
    )
    matrix = manual @ base
    if np.allclose(matrix, np.eye(3), atol=1e-10):
        return image
    output_size = _crop_geometry(matrix, image.size, aspect)
    width, height = image.size
    short = min(image.size)
    to_pixels = np.array([[short, 0, width / 2], [0, short, height / 2], [0, 0, 1]])
    from_output = np.array(
        [
            [1 / short, 0, -output_size[0] / (2 * short)],
            [0, 1 / short, -output_size[1] / (2 * short)],
            [0, 0, 1],
        ]
    )
    inverse = to_pixels @ np.linalg.inv(matrix) @ from_output
    inverse /= inverse[2, 2]
    return image.transform(
        output_size,
        Image.Transform.PERSPECTIVE,
        tuple(inverse.ravel()[:8]),
        Image.Resampling.BICUBIC,
    )


def _vertical_lines(sample):
    """Find long near-vertical edges using a bounded Hough vote."""
    gray = np.asarray(sample.filter(ImageFilter.GaussianBlur(0.7)), dtype=np.float32)
    height, width = gray.shape
    gx = (gray[1:-1, 2:] - gray[1:-1, :-2]) * 0.5
    gy = (gray[2:, 1:-1] - gray[:-2, 1:-1]) * 0.5
    strength = np.abs(gx)
    mask = (strength >= max(9, float(np.percentile(strength, 85)))) & (
        np.abs(gy) < strength * 0.7
    )
    mask[:, 1:-1] &= (strength[:, 1:-1] >= strength[:, :-2]) & (
        strength[:, 1:-1] >= strength[:, 2:]
    )
    margin = max(3, min(width, height) // 40)
    mask[:margin] = False
    mask[-margin:] = False
    mask[:, :margin] = False
    mask[:, -margin:] = False
    ys, xs = np.nonzero(mask)
    weights = np.minimum(strength[ys, xs], 40)
    if len(xs) < height * 0.5:
        return []
    if len(xs) > 30000:
        indices = np.argpartition(weights, -30000)[-30000:]
        xs, ys, weights = xs[indices], ys[indices], weights[indices]
    xs, ys = xs.astype(float) + 1, ys.astype(float) + 1
    offset = height
    peaks = []
    for slope in np.arange(-0.45, 0.451, 0.005):
        intercept = np.rint(xs - slope * ys).astype(int) + offset
        votes = np.bincount(
            intercept, weights=weights, minlength=width + 2 * height + 4
        )
        votes = np.convolve(votes, [1, 1, 1], mode="same")
        for _ in range(3):
            peak = int(np.argmax(votes))
            score = votes[peak]
            if score < height * 5:
                break
            peaks.append((float(score), float(slope), peak - offset))
            votes[max(0, peak - 8) : peak + 9] = 0
    candidates = []
    for score, slope, intercept in sorted(peaks, reverse=True):
        center = intercept + slope * height / 2
        if any(abs(center - width / 2 - c[1]) < 12 for c in candidates):
            continue
        near = np.abs(xs - slope * ys - intercept) <= 2
        rows = np.unique(ys[near].astype(int))
        if len(rows) < height * 0.16 or np.ptp(rows) < height * 0.22:
            continue
        bands = np.bincount(np.minimum(rows * 10 // height, 9), minlength=10)
        if np.count_nonzero(bands >= height * 0.015) < 3:
            continue
        fitted = np.polyfit(
            ys[near] - height / 2, xs[near] - width / 2, 1, w=weights[near]
        )
        candidates.append((float(fitted[0]), float(fitted[1]), score))
        if len(candidates) >= 18:
            break
    return candidates


def _family(sample):
    candidates = _vertical_lines(sample)
    if len(candidates) < 3:
        return None
    slope, position, weight = np.array(candidates).T
    short = min(sample.size)
    position /= short
    best = None
    for i, j in combinations(range(len(slope)), 2):
        if abs(position[i] - position[j]) < sample.width / short * 0.25:
            continue
        q = (slope[i] - slope[j]) / (position[i] - position[j])
        a = slope[i] - q * position[i]
        if abs(q) > 1 or abs(a) > 0.35:
            continue
        agrees = np.abs(slope - (a + q * position)) < 0.018
        if (
            np.count_nonzero(agrees) < 3
            or np.ptp(position[agrees]) < sample.width / short * 0.3
        ):
            continue
        score = float(weight[agrees].sum())
        if best is None or score > best[0]:
            best = (score, agrees)
    if best is None or best[0] < weight.sum() * 0.55:
        return None
    keep = best[1]
    design = np.column_stack((np.ones(np.count_nonzero(keep)), position[keep]))
    a, q = np.linalg.lstsq(
        design * np.sqrt(weight[keep, None]),
        slope[keep] * np.sqrt(weight[keep]),
        rcond=None,
    )[0]
    return float(a), float(q)


def auto_geometry(image, mode):
    if mode not in {"vertical", "auto", "full"}:
        raise ValueError("Unknown automatic geometry mode.")
    sample = image.convert("L")
    sample.thumbnail((720, 720), Image.Resampling.LANCZOS)
    if min(sample.size) < 64:
        raise ValueError("Photo is too small for automatic correction. Use Guided.")
    vertical = _family(sample)
    horizontal = (
        _family(sample.transpose(Image.Transpose.TRANSPOSE))
        if mode != "vertical"
        else None
    )
    if mode == "vertical" and vertical is None:
        raise ValueError(
            "No reliable vertical edges found. Use Guided on two building edges."
        )
    if mode == "full" and (vertical is None or horizontal is None):
        raise ValueError(
            "Full correction needs reliable edges in both directions. Try Vertical or Guided."
        )
    if vertical is None and horizontal is None:
        raise ValueError("No reliable perspective found. Use Guided.")
    matrix = _upright(vertical, horizontal)
    try:
        _crop_geometry(matrix, image.size)
    except ValueError:
        if mode != "auto" or vertical is None:
            raise
        matrix = _upright(vertical)
        _crop_geometry(matrix, image.size)
    return tuple(matrix.ravel())
