"""Synthetic media for contract tests only; never evidence of a model run."""
from PIL import Image


def write_test_png(path, size=(320, 480)):
    Image.new("RGB", size, "#D9E7FF").save(path, format="PNG")
