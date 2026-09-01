"""Development tooling: the mechanics behind the release workflows.

This package lives in `automation/`, outside `src/`, so it is never packaged
into the distribution and never imported by gaxi itself. The root `tasks.py`
puts it on the path for invoke; pytest does the same through `pythonpath`.
"""
