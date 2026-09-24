# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline, provenance-preserving kernel vocabulary miner.

Extracts lexical facts, not C semantics. Comments/string contents are masked
before matching. Symbolic arguments remain symbolic; no API occurrence grants
read/write safety, device support, a report size, or semantic meaning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from .evidence_graph import EvidenceGraph, EvidenceNode

ROOTS = ('drivers/hid/', 'drivers/input/', 'drivers/bluetooth/',
         'tools/testing/selftests/hid/')
TOKENS = re.compile(r'\b(?:HID_REQ_(?:GET|SET)_REPORT|HID_(?:FEATURE|INPUT|OUTPUT)_REPORT|'
                    r'hid_hw_(?:raw_request|output_report|request)|usb_control_msg|'
                    r'USB_(?:DEVICE|INTERFACE_INFO)|HID_(?:USB|BLUETOOTH)_DEVICE|'
                    r'(?:get|put)_unaligned_(?:le|be)(?:16|32)|'
                    r'cpu_to_(?:le|be)(?:16|32)|(?:le|be)(?:16|32)_to_cpu|'
                    r'crc(?:8|16|32)|msleep|usleep_range)\b')
MASK = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)


def mine_source(text: str, *, path: str, revision: str) -> EvidenceGraph:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or '..' in parsed.parts or not path.startswith(ROOTS):
        raise ValueError('source outside supported kernel trees')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('pin source to a full kernel commit SHA')
    if len(text) > 4_000_000:
        raise ValueError('source exceeds mining bound')
    graph = EvidenceGraph()
    digest = hashlib.sha256(text.encode()).hexdigest()
    url = f'https://github.com/torvalds/linux/blob/{revision}/{path}'
    root = graph.add(EvidenceNode('source', f'sha256:{digest}', url))
    masked = MASK.sub(lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), text)
    for number, line in enumerate(masked.splitlines(), 1):
        for token in sorted(set(TOKENS.findall(line))):
            graph.add(EvidenceNode('kernel_fact', json.dumps({'token': token, 'line': number}, sort_keys=True),
                                   f'{url}#L{number}', (root,)))
    # Parse only explicit literal enum members; unresolved C expressions stay
    # symbolic instead of being evaluated or inferred from neighboring values.
    for enum in re.finditer(r'\benum\s*(?:\w+\s*)?\{([^{}]*)\}', masked, re.S):
        for member in re.finditer(r'\b([A-Za-z_]\w*)\s*=\s*(0[xX][0-9a-fA-F]+|[0-9]+)\s*(?=,|$)', enum.group(1)):
            literal = member.group(2)
            # Leading-zero C octal is deliberately not interpreted as decimal.
            if len(literal) > 1 and literal.startswith('0') and not literal.lower().startswith('0x'):
                continue
            line = masked.count('\n', 0, enum.start(1) + member.start()) + 1
            claim = {'enum_member': member.group(1), 'value': int(literal, 16 if literal.lower().startswith('0x') else 10), 'line': line}
            graph.add(EvidenceNode('kernel_fact', json.dumps(claim, sort_keys=True), f'{url}#L{line}', (root,)))
    return graph


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--kernel-path', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    graph = mine_source(args.source.read_text(), path=args.kernel_path, revision=args.revision)
    graph.save(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
