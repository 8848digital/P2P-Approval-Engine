# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import sys

MAX_LINES = 250


def main(argv):
	files = argv[1:]
	for file_path in files:
		# file_path comes from pre-commit's own staged-file list, not user/network input.
		with open(file_path) as file:  # nosemgrep: frappe-security-file-traversal
			lines = file.readlines()
			if len(lines) > MAX_LINES:
				print(f"Error: File {file_path} has more than {MAX_LINES} lines.")
				sys.exit(1)


if __name__ == "__main__":
	main(sys.argv)
