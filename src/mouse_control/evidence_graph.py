"""Content-addressed Discovery evidence DAG, persisted as knowledge, not authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


KINDS = frozenset({'identity', 'interface', 'report', 'frame', 'transaction',
                   'state', 'hypothesis', 'experiment', 'verification', 'capability',
                   'source', 'kernel_fact'})


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class EvidenceNode:
    kind: str
    claim: str
    source: str
    parents: tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in KINDS or not self.claim.strip() or not self.source.strip():
            raise ValueError('typed claim and provenance are required')
        if len(set(self.parents)) != len(self.parents):
            raise ValueError('duplicate evidence dependencies')

    @property
    def identifier(self) -> str:
        return hashlib.sha256(_canonical(self.as_dict()).encode()).hexdigest()

    def as_dict(self) -> dict:
        return {'kind': self.kind, 'claim': self.claim, 'source': self.source,
                'parents': list(self.parents)}


class EvidenceGraph:
    """Append-only DAG with transitive invalidation; no stored write receipts.

    Hashes detect accidental edits, not malicious authors. Sources and experiment
    assertions remain untrusted knowledge even if their hashes are intact.
    """

    def __init__(self):
        self._nodes: dict[str, EvidenceNode] = {}
        self._invalid: dict[str, str] = {}

    @property
    def valid_ids(self) -> frozenset[str]:
        return frozenset(self._nodes.keys() - self._invalid.keys())

    def add(self, node: EvidenceNode) -> str:
        if any(parent not in self._nodes for parent in node.parents):
            raise ValueError('unresolved evidence dependency')
        key = node.identifier
        self._nodes[key] = node
        if any(parent in self._invalid for parent in node.parents):
            self._invalid[key] = 'dependency invalidated'
        return key

    def invalidate(self, identifier: str, reason: str) -> None:
        if identifier not in self._nodes or not reason.strip():
            raise ValueError('existing evidence and reason required')
        self._invalid[identifier] = reason
        # Insertion order is topological because add requires existing parents.
        for key, node in self._nodes.items():
            if any(parent in self._invalid for parent in node.parents):
                self._invalid.setdefault(key, 'dependency invalidated')

    def explain(self, identifier: str) -> tuple[dict, ...]:
        """Return supporting ancestry in topological order with revocation reasons."""
        needed = set()
        pending = [identifier]
        while pending:
            key = pending.pop()
            if key not in needed:
                needed.add(key)
                pending.extend(self._nodes[key].parents)
        return tuple({'id': key, **node.as_dict(), 'invalid': self._invalid.get(key)}
                     for key, node in self._nodes.items() if key in needed)

    def dumps(self) -> str:
        return _canonical({'schema': 1, 'nodes': [
            {'id': key, **node.as_dict()} for key, node in self._nodes.items()],
            'invalid': self._invalid})

    @classmethod
    def loads(cls, text: str) -> 'EvidenceGraph':
        if len(text) > 8_000_000:
            raise ValueError('evidence graph exceeds import bound')
        try:
            document = json.loads(text)
            if set(document) != {'schema', 'nodes', 'invalid'} or type(document['schema']) is not int or document['schema'] != 1:
                raise ValueError('unsupported evidence graph schema')
            if (not isinstance(document['nodes'], list) or len(document['nodes']) > 100_000
                    or not isinstance(document['invalid'], dict)
                    or len(document['invalid']) > 100_000):
                raise ValueError('evidence graph collections exceed import bounds')
            graph = cls()
            for row in document['nodes']:
                if set(row) != {'id', 'kind', 'claim', 'source', 'parents'} or not isinstance(row['parents'], list):
                    raise ValueError('malformed evidence node')
                if any(not isinstance(v, str) for v in (row['id'], row['kind'], row['claim'], row['source'], *row['parents'])):
                    raise ValueError('evidence node fields must be strings')
                node = EvidenceNode(row['kind'], row['claim'], row['source'], tuple(row['parents']))
                if node.identifier != row['id'] or row['id'] in graph._nodes:
                    raise ValueError('altered or duplicate evidence node')
                graph.add(node)
            for key, reason in document['invalid'].items():
                if not isinstance(key, str) or not isinstance(reason, str) or not reason.strip():
                    raise ValueError('malformed evidence invalidation')
                graph.invalidate(key, reason)
            return graph
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError('malformed evidence graph') from exc

    def save(self, path: Path) -> None:
        """Create a new immutable snapshot; never overwrite another snapshot."""
        with path.open('x', encoding='utf-8') as output:
            output.write(self.dumps() + '\n')
