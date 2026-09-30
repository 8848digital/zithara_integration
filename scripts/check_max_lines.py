# Copyright (c) 2026 8848 Digital LLP. All rights reserved.
# Proprietary and confidential. Unauthorized copying, distribution, or use
# of this file, via any medium, is strictly prohibited without prior
# written permission from 8848 Digital LLP.

import sys

MAX_LINES = 250


def main(argv):
	"""
	Fail the pre-commit run if any given Python file exceeds MAX_LINES.

	Parameters:
	        argv (list[str], required): sys.argv; argv[1:] are the file paths to check.

	Returns:
	        None. Exits with status 1 on the first file over the limit.
	"""
	files = argv[1:]
	for file_path in files:
		with open(file_path) as file:
			lines = file.readlines()
			if len(lines) > MAX_LINES:
				print(f"Error: File {file_path} has more than {MAX_LINES} lines.")
				sys.exit(1)


if __name__ == "__main__":
	main(sys.argv)
