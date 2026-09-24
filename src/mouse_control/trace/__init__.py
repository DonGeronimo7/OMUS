# SPDX-License-Identifier: AGPL-3.0-or-later
"""Protocol-neutral USB trace evidence.

This package is intentionally observation-only.  Captured traffic can become
evidence for a protocol hypothesis, but nothing here authorizes or executes a
hardware write.
"""

from .models import (
    CaptureQuality,
    CaptureSource,
    CompletenessStatus,
    TransactionAnomaly,
    UrbEventType,
    UsbDirection,
    UsbObservation,
    UsbSetupPacket,
    UsbTransaction,
    UsbTransferType,
)
from .transaction_assembler import UsbTransactionAssembler
from .hid_enrichment import HidTraceEnrichment

__all__ = [
    "CaptureSource",
    "CaptureQuality",
    "CompletenessStatus",
    "TransactionAnomaly",
    "UrbEventType",
    "UsbDirection",
    "UsbObservation",
    "UsbSetupPacket",
    "UsbTransaction",
    "UsbTransactionAssembler",
    "UsbTransferType",
    "HidTraceEnrichment",
]
