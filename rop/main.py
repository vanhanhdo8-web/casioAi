from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


MODEL_LINE_RE = re.compile(r"^\s*([0-9A-F]+:[0-9A-F]{4}H)\s+([0-9A-F]+)\s+(.*?)\s*$", re.IGNORECASE)
COLON_ADDRESS_RE = re.compile(r"^([0-9A-F]+):([0-9A-F]{4})(?:H)?$", re.IGNORECASE)
RAW_ADDRESS_RE = re.compile(r"^([0-9A-F])([0-9A-F]{4})(?:H)?$", re.IGNORECASE)
PACKED_HEX_RE = re.compile(r"^(?:[0-9A-F]{8}|(?:[0-9A-F]{2}\s+){3}[0-9A-F]{2})$", re.IGNORECASE)


@dataclass(frozen=True)
class ModelEntry:
    index: int
    address_text: str
    segment: int
    address: int
    opcode: str
    opcode_key: str


@dataclass(frozen=True)
class TranslationResult:
    source_entry: ModelEntry
    target_entry: ModelEntry
    score: int
    total_checks: int

    @property
    def confidence(self) -> int:
        if self.total_checks <= 0:
            return 0
        return round((self.score / self.total_checks) * 100)


class Model:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._load_entries(path)
        self.by_address = {entry.address_text.upper(): entry for entry in self.entries}
        self.by_opcode_key = {}
        for entry in self.entries:
            self.by_opcode_key.setdefault(entry.opcode_key, []).append(entry)

    @staticmethod
    def _load_entries(path: Path) -> list[ModelEntry]:
        entries: list[ModelEntry] = []
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = MODEL_LINE_RE.match(raw_line)
            if not match:
                continue
            address_text, opcode, _ = match.groups()
            segment_text, address_hex = address_text[:-1].split(":", 1)
            entries.append(
                ModelEntry(
                    index=len(entries),
                    address_text=format_address(int(segment_text, 16), int(address_hex, 16)),
                    segment=int(segment_text, 16),
                    address=int(address_hex, 16),
                    opcode=opcode.upper(),
                    opcode_key=opcode[:4].upper(),
                )
            )
        if not entries:
            raise ValueError(f"No model entries could be read from {path}")
        return entries

    def get_by_address(self, address_text: str) -> ModelEntry | None:
        return self.by_address.get(address_text.upper())


def format_address(segment: int, address: int) -> str:
    return f"{segment:X}:{address:04X}H"


def normalize_address_input(text: str) -> str:
    cleaned = text.strip().upper()
    colon_match = COLON_ADDRESS_RE.fullmatch(cleaned)
    if colon_match:
        return format_address(int(colon_match.group(1), 16), int(colon_match.group(2), 16))

    raw_match = RAW_ADDRESS_RE.fullmatch(cleaned)
    if raw_match:
        return format_address(int(raw_match.group(1), 16), int(raw_match.group(2), 16))

    raise ValueError(f"Not a recognized address: {text}")


def decode_packed_hex_address(text: str) -> str:
    stripped = text.strip().upper()
    digits = re.sub(r"\s+", "", stripped)
    if not PACKED_HEX_RE.fullmatch(stripped):
        raise ValueError(f"Not a recognized packed hex address: {text}")

    segment = int(digits[5], 16)
    address = int(digits[2] + digits[3] + digits[0] + digits[1], 16)
    address &= ~1
    return format_address(segment, address)


def score_candidate(source: Model, target: Model, source_entry: ModelEntry, target_entry: ModelEntry) -> tuple[int, int]:
    offsets = [0, -1, 1, -2, 2, -3, 3]
    score = 0
    total_checks = 0

    for offset in offsets:
        source_index = source_entry.index + offset
        target_index = target_entry.index + offset
        if source_index < 0 or target_index < 0:
            continue
        if source_index >= len(source.entries) or target_index >= len(target.entries):
            continue
        total_checks += 1
        if source.entries[source_index].opcode_key == target.entries[target_index].opcode_key:
            score += 1

    return score, total_checks


def translate_entry(source: Model, target: Model, source_entry: ModelEntry) -> TranslationResult | None:
    candidates = target.by_opcode_key.get(source_entry.opcode_key, [])
    best: TranslationResult | None = None

    for candidate in candidates:
        score, total_checks = score_candidate(source, target, source_entry, candidate)
        result = TranslationResult(source_entry=source_entry, target_entry=candidate, score=score, total_checks=total_checks)
        if best is None:
            best = result
            continue
        if result.score > best.score:
            best = result
            continue
        if result.score == best.score and result.total_checks > best.total_checks:
            best = result

    return best


def translate_address(source: Model, target: Model, address_text: str) -> str:
    source_entry = source.get_by_address(address_text)
    if source_entry is None:
        return f"{address_text} -> source address not found"

    result = translate_entry(source, target, source_entry)
    if result is None:
        return f"{address_text} -> no translation found"

    return f"{address_text} -> {result.target_entry.address_text} ({result.confidence}%)"


def translate_input_line(source: Model, target: Model, raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""

    try:
        upper_line = line.upper()
        if COLON_ADDRESS_RE.fullmatch(upper_line) or RAW_ADDRESS_RE.fullmatch(upper_line):
            return translate_address(source, target, normalize_address_input(line))
        if PACKED_HEX_RE.fullmatch(upper_line):
            return translate_address(source, target, decode_packed_hex_address(line))
        return f"{line} -> input must be an address or packed hex"
    except ValueError as error:
        return f"{line} -> {error}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate ROP gadgets between calculator models.")
    parser.add_argument("source_model", help="Model to translate from")
    parser.add_argument("target_model", help="Model to translate to")
    return parser


def resolve_model_path(models_dir: Path, model_name: str) -> Path:
    # Thêm .txt vào tên file
    model_file = model_name + '.txt'
    path = models_dir / model_file
    if not path.is_file():
        available = ", ".join(sorted(item.name for item in models_dir.iterdir() if item.is_file()))
        raise FileNotFoundError(f"Unknown model '{model_name}'. Available models: {available}")
    return path


def interactive_loop(source: Model, target: Model) -> int:
    print("Enter gadgets as addresses or packed hex. Type 'done' to finish.")
    try:
        while True:
            try:
                line = input().strip()
            except EOFError:
                return 0

            if line.lower() in {"done", "end", "quit", "exit"}:
                return 0

            translated = translate_input_line(source, target, line)
            if translated:
                print(translated)
    except KeyboardInterrupt:
        print()
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Đường dẫn đến thư mục model (không có 's' ở cuối)
    repo_root = Path(__file__).resolve().parent
    model_dir = repo_root / "model"  # /rop/model/ (không phải models)

    try:
        source_path = resolve_model_path(model_dir, args.source_model)
        target_path = resolve_model_path(model_dir, args.target_model)
        source_model = Model(source_path)
        target_model = Model(target_path)
    except (FileNotFoundError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    return interactive_loop(source_model, target_model)


if __name__ == "__main__":
    raise SystemExit(main())
