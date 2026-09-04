"""Helpers shared by the numbered pipeline steps.

The steps are named `NN_thing.py` so the order of the pipeline is readable from
a directory listing. That naming also makes them un-importable, so anything two
steps both need lives here instead of being copied into both.
"""
