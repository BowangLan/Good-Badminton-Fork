"""Reusable dataset loaders for benchmark plugins."""

import glob
import os

from .types import Sample

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")


def load_image_folder(data_dir, recursive=True):
    """Return one `Sample` per image file under *data_dir*.

    Images are NOT loaded here — only paths are recorded, so strategies control
    how/when to read them. Sample ids are the path relative to *data_dir* with
    separators flattened, so they're safe to use in filenames.
    """
    if not data_dir or not os.path.isdir(data_dir):
        return []

    paths = []
    pattern = os.path.join(data_dir, "**", "*") if recursive else os.path.join(data_dir, "*")
    for path in glob.glob(pattern, recursive=recursive):
        if os.path.isfile(path) and path.lower().endswith(IMAGE_EXTS):
            paths.append(path)

    samples = []
    for path in sorted(paths):
        rel = os.path.relpath(path, data_dir)
        sample_id = rel.replace(os.sep, "__")
        samples.append(Sample(id=sample_id, path=path, meta={"rel": rel}))
    return samples
