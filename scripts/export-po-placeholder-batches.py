#!/usr/bin/env python3
"""Export msgstr==msgid PO placeholders into translation batches."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PoEntry:
    msgid: str
    msgstr: str
    comments: list[str] = field(default_factory=list)


def po_unquote(text: str) -> str:
    return ast.literal_eval(text)


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


class PoCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._read_entries()

    def placeholders(self) -> list[PoEntry]:
        return [
            entry for entry in self.entries
            if entry.msgid != "" and entry.msgstr == entry.msgid
        ]

    def _read_entries(self) -> list[PoEntry]:
        entries: list[PoEntry] = []
        comments: list[str] = []
        msgid: str | None = None
        msgstr: str | None = None
        active: str | None = None

        def flush() -> None:
            nonlocal comments, msgid, msgstr, active
            if msgid is not None and msgid != "":
                entries.append(PoEntry(msgid, msgstr or "", comments))
            comments = []
            msgid = None
            msgstr = None
            active = None

        for line_no, raw_line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                flush()
                continue
            if line.startswith("#"):
                comments.append(raw_line)
                continue
            if line.startswith("msgid "):
                flush()
                msgid = po_unquote(line[6:].strip())
                active = "msgid"
                continue
            if line.startswith("msgstr "):
                if msgid is None:
                    raise ValueError(f"{self.path}:{line_no}: msgstr before msgid")
                msgstr = po_unquote(line[7:].strip())
                active = "msgstr"
                continue
            if line.startswith('"') and active == "msgid":
                msgid = (msgid or "") + po_unquote(line)
                continue
            if line.startswith('"') and active == "msgstr":
                msgstr = (msgstr or "") + po_unquote(line)
                continue
            raise ValueError(f"{self.path}:{line_no}: unsupported PO line: {raw_line}")
        flush()
        return entries


class BatchWriter:
    def __init__(self, output_dir: Path, language: str, batch_size: int) -> None:
        self.output_dir = output_dir
        self.language = language
        self.batch_size = batch_size

    def write_domain(self, domain: str, entries: list[PoEntry]) -> dict[str, object]:
        batches = [
            entries[index:index + self.batch_size]
            for index in range(0, len(entries), self.batch_size)
        ]
        total_batches = len(batches)
        files: list[str] = []
        for index, batch in enumerate(batches, start=1):
            path = self.output_dir / domain / f"{domain}-{self.language}-{index:03d}.po"
            self._write_batch(path, domain, batch, index, total_batches)
            files.append(path.as_posix())
        return {
            "domain": domain,
            "entries": len(entries),
            "batch_size": self.batch_size,
            "batches": total_batches,
            "files": files,
        }

    def _write_batch(self, path: Path, domain: str, entries: list[PoEntry], batch_index: int, total_batches: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Translation batch for Path of Building data domain: {domain}.",
            "# Fill msgstr only. Do not change msgid, comments, ordering, placeholders, or color escapes.",
            "# This batch was generated from canonical PO entries whose msgstr equals msgid.",
            f"# Batch {batch_index} of {total_batches}.",
            'msgid ""',
            'msgstr ""',
            '"Project-Id-Version: Path of Building PoE2 data translation batch\\n"',
            '"Content-Type: text/plain; charset=UTF-8\\n"',
            '"Content-Transfer-Encoding: 8bit\\n"',
            f'"Language: {self.language}\\n"',
            "",
        ]
        for entry in entries:
            lines.extend(entry.comments)
            lines.append(f"msgid {po_quote(entry.msgid)}")
            lines.append('msgstr ""')
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


class PlaceholderBatchExporter:
    def __init__(self, po_paths: list[Path], output_dir: Path, language: str, batch_size: int) -> None:
        self.po_paths = po_paths
        self.output_dir = output_dir
        self.writer = BatchWriter(output_dir, language, batch_size)

    def run(self) -> int:
        manifest: list[dict[str, object]] = []
        for po_path in self.po_paths:
            domain = po_path.stem
            entries = PoCatalog(po_path).placeholders()
            summary = self.writer.write_domain(domain, entries)
            manifest.append(summary)
            print(f"{domain}: exported {summary['entries']} entries into {summary['batches']} batches")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "manifest.json").write_text(
            json.dumps({"domains": manifest}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        total_entries = sum(int(item["entries"]) for item in manifest)
        total_batches = sum(int(item["batches"]) for item in manifest)
        print(f"total: exported {total_entries} entries into {total_batches} batches")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--po", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--language", default="zh_TW")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()
    return PlaceholderBatchExporter(args.po, args.output_dir, args.language, args.batch_size).run()


if __name__ == "__main__":
    raise SystemExit(main())
