# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""Masking of Aadhaar-like values in KYC request/response logs. Split out
of vendor_check_http.py to keep that file under the line-count cap.
"""

import json

# Field names (by convention) that should be masked in stored logs even if an
# admin forgets to list them explicitly - belt and suspenders for Aadhaar etc.
SENSITIVE_KEY_HINTS = ("aadhaar", "aadhar", "adhar")


def _mask(value: str) -> str:
	"""Mask all but the last 4 characters of value with asterisks."""
	value = str(value)
	if len(value) <= 4:
		return "*" * len(value)
	return "*" * (len(value) - 4) + value[-4:]


def mask_sensitive(payload_str: str, field_map) -> str:
	"""Best-effort masking of Aadhaar-like values inside a JSON string before it
	is written to the log, controlled by KYC Settings.mask_sensitive_data_in_logs."""
	try:
		data = json.loads(payload_str)
	except Exception:
		return payload_str

	def walk(obj):
		if isinstance(obj, dict):
			for k, v in obj.items():
				if isinstance(v, str) and any(h in k.lower() for h in SENSITIVE_KEY_HINTS):
					obj[k] = _mask(v)
				elif isinstance(v, dict | list):
					walk(v)
		elif isinstance(obj, list):
			for item in obj:
				walk(item)

	walk(data)
	return json.dumps(data, indent=2)
