"""Internal HTTP server submodule for `wbauth serve` (CLI-05, D-50).

Stdlib http.server only — NO Flask, NO FastAPI, NO Starlette.
The 30-LOC executable budget is enforced by the plan's acceptance gate.
This module is internal (leading underscore) so it doesn't show up in
`from wbauth import *` and isn't part of the public API surface.
"""
