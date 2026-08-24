"""Read-only, static architecture explorer for Python source trees."""

from .analyzer import analyse_source_tree
from .renderer import build_architecture_viewer

__all__ = ["analyse_source_tree", "build_architecture_viewer"]
