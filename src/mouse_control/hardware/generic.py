# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compatibility import for the former generic fallback.

The inert GenericBackend has been replaced by :class:`DiscoveryBackend`.
Keeping this alias avoids breaking third-party imports while ensuring every
fallback device now enters the automatic discovery path.
"""

from .discovery_backend import DiscoveryBackend

GenericBackend = DiscoveryBackend

__all__ = ["GenericBackend", "DiscoveryBackend"]
