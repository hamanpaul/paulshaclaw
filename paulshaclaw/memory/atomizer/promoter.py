from __future__ import annotations

from abc import ABC, abstractmethod

from . import slice_frontmatter
from .config import AtomizerConfig
from .slice_frontmatter import Slice
from .splitter import Fragment


class Promoter(ABC):
    """Maps one fragment to one or more knowledge slices.

    The MVP IdentityPromoter is 1:1. A future LLM promoter (T3.2) replaces only
    this seam to perform semantic split/merge, relation inference, and tagging.
    """

    @abstractmethod
    def promote(self, fragment: Fragment, config: AtomizerConfig) -> list[Slice]:
        ...


class IdentityPromoter(Promoter):
    def promote(self, fragment: Fragment, config: AtomizerConfig) -> list[Slice]:
        return [slice_frontmatter.build(fragment, config)]
