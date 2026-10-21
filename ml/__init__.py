"""Per-square piece classifier: shared crop and label code first, torch code in submodules.

Importing `ml` or `ml.common` must stay free of torch so the edge client can use them.
"""
