from __future__ import annotations

import argparse
from pathlib import Path
import random
from string import ascii_lowercase


def _build_random_derangement() -> dict[str, str]:
	source_letters = list(ascii_lowercase)
	shuffled_letters = source_letters.copy()
	system_random = random.SystemRandom()

	while True:
		system_random.shuffle(shuffled_letters)
		if all(original != shuffled for original, shuffled in zip(source_letters, shuffled_letters)):
			return dict(zip(source_letters, shuffled_letters, strict=True))


def encode_plaintext_lines(
	plain_text_file_path: str | Path,
	beginning_pattern: str,
	output_directory_path: str | Path,
) -> list[tuple[Path, Path]]:
	input_path = Path(plain_text_file_path)
	if not input_path.exists() or not input_path.is_file():
		raise FileNotFoundError(f"Input file not found: {input_path}")

	if not beginning_pattern or not beginning_pattern.strip():
		raise ValueError("beginning_pattern must be a non-empty string")

	output_path = Path(output_directory_path)
	output_path.mkdir(parents=True, exist_ok=True)

	lines = input_path.read_text(encoding="utf-8", errors="replace").splitlines()

	written_files: list[tuple[Path, Path]] = []
	for index, line in enumerate(lines):
		normalized_line = line.lower()
		substitution_map = _build_random_derangement()

		encoded_line = "".join(
			substitution_map[character] if character in substitution_map else character
			for character in normalized_line
		)

		encoded_file = output_path / f"{beginning_pattern}_{index}.txt"
		solution_file = output_path / f"{beginning_pattern}_{index}_solution.txt"

		encoded_file.write_text(encoded_line, encoding="utf-8")
		solution_file.write_text(normalized_line, encoding="utf-8")

		written_files.append((encoded_file, solution_file))

	return written_files


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Encode one plaintext message per line into cryptogram files with matching solution files.",
	)
	parser.add_argument("plain_text_file_path", help="Path to input plaintext file (one message per line)")
	parser.add_argument("beginning_pattern", help="File name prefix for output files")
	parser.add_argument("output_directory_path", help="Directory to write encoded and solution files")
	return parser


def main() -> None:
	parser = _build_parser()
	args = parser.parse_args()

	generated_files = encode_plaintext_lines(
		plain_text_file_path=args.plain_text_file_path,
		beginning_pattern=args.beginning_pattern,
		output_directory_path=args.output_directory_path,
	)

	print(f"Generated {len(generated_files)} encoded files and {len(generated_files)} solution files.")


if __name__ == "__main__":
	main()
