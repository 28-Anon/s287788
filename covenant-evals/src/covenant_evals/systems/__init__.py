"""Systems under test.

A *system* is anything that takes a document and a question and returns an answer with a
citation. The baseline is one API call. Later there will be a retrieval variant and a
tool-using agent, and the harness will not care which is which.
"""

from .baseline import Answer, BaselineSystem

__all__ = ["Answer", "BaselineSystem"]
