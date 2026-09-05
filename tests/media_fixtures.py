"""Synthetic media for contract tests only; never evidence of a model run."""
from PIL import Image


def write_test_png(path):
    Image.new("RGB", (320, 180), "#D9E7FF").save(path, format="PNG")
