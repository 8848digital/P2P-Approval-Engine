# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

"""URL-safe email encoding for vendor onboarding links. Split out of
vendor_mail.py to keep that file under the line-count cap - used by both
vendor_mail.py and vendor_reminder.py.
"""

import base64


def encode_email(email: str) -> str:
	"""
	Base64url-encode the local and domain parts of an email address
	independently, so the address survives being embedded in a URL query
	param without further escaping.

	Parameters:
	        email (str, required): Email address in "local@domain" form.

	Returns:
	        str: "<encoded_local>@<encoded_domain>"
	"""
	local, domain = email.split("@")
	encoded_local = encode_string_part(local)
	encoded_domain = encode_string_part(domain)
	encoded_email = f"{encoded_local}@{encoded_domain}"
	return encoded_email


def encode_string_part(part: str) -> str:
	"""
	Base64url-encode a single string, stripping padding.

	Parameters:
	        part (str, required): String to encode.

	Returns:
	        str: URL-safe base64 encoding of `part`, without `=` padding.
	"""
	encoded_part = base64.urlsafe_b64encode(part.encode()).decode().rstrip("=")
	return encoded_part
