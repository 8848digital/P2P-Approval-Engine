# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.
"""Standard response envelope shared by every module's ``api/vN`` endpoints.

All whitelisted endpoints wrap their payload in :func:`api_response` so clients
see one consistent shape (``{"success": ..., "data": ...}``) across the whole
app. Only successful payloads are wrapped here — exceptions are left to
propagate as normal Frappe errors so the framework's HTTP error handling (and
the desk client's ``.catch``/error toast) keeps working unchanged.
"""


def api_response(data=None, success=True):
    """Wrap an endpoint payload in the app's standard response envelope.

    Parameters:
        data (any, optional): The payload to return to the client. Defaults to
            ``None``.
        success (bool, optional): Whether the call succeeded. Defaults to
            ``True``.

    Returns:
        dict: ``{"success": success, "data": data}``.
    """
    return {"success": success, "data": data}
