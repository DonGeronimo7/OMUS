"""Known protocol-family repertoire and conservative structural matcher.

The repertoire is intentionally *not* a device support table.  It records
reusable grammar facts learned from maintained open-source implementations and
hardware verification.  Structural matches help discovery decide what to
observe next; they never grant write permission on their own.

Source links, license-review status, and unresolved attribution work are kept
in ``CREDITS.md``. A cited protocol fact is not a bundled upstream code file,
and a family match never grants write authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from .discovery_models import DeviceNode, PhysicalDevice
from .hid_descriptor import ParsedHidDescriptor
from .protocol_codec import ProtocolCodecError, decode_value
from .protocol_grammar import (
    CodecKind,
    CodecSpec,
    DiscriminatorKind,
    EvidenceCategory,
    FieldBinding,
    FrameSide,
    ProtocolFamily,
    ProtocolSource,
    RecognitionRecipe,
    ReportSignature,
    SemanticDiscriminator,
    SessionGrammar,
    SemanticBehavior,
    SourceTrust,
    TransportKind,
    WriteScope,
)


@dataclass(frozen=True)
class SemanticExchange:
    request: bytes
    response: bytes
    request_report_id: int | None = None
    response_report_id: int | None = None


@dataclass(frozen=True)
class SemanticFamilyRecognition:
    candidate: FamilyCandidate
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    semantic_records: tuple[bytes, ...]
    evidence_categories: tuple[EvidenceCategory, ...] = ()

    @property
    def recognized(self) -> bool:
        recipe = self.candidate.family.recognition
        return (
            recipe is not None
            and bool(self.matched)
            and not self.missing
            and len(self.evidence_categories) >= recipe.minimum_independent_categories
        )

    @property
    def write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class FamilyCandidate:
    family: ProtocolFamily
    score: int
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    exact_identity: bool

    @property
    def write_authorized(self) -> bool:
        # A structural match is not a proven family handshake.  Backends and
        # later active validation may promote that separately.
        return self.family.can_authorize_write(exact_model=self.exact_identity)


class RecognitionStatus(str, Enum):
    UNKNOWN = "unknown"
    CANDIDATE = "candidate"
    AMBIGUOUS = "ambiguous"
    RECOGNIZED = "recognized"


@dataclass(frozen=True)
class OpenSetRecognition:
    status: RecognitionStatus
    family: str | None
    ranked: tuple[SemanticFamilyRecognition, ...]
    reason: str

    @property
    def write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class ObservedReport:
    node: DeviceNode
    report_type: str
    report_id: int
    byte_length: int
    vendor_usage: bool
    usage_pages: tuple[int, ...] = ()
    application_usages: tuple[tuple[int, int], ...] = ()
    interface_number: int | None = None


@dataclass(frozen=True)
class RedragonDpiEncoding:
    value: int
    range_flag: int


@dataclass(frozen=True)
class RyunixTelemetry:
    active: bool
    dpi_stage: int
    polling_rate_hz: int
    battery_percent: int
    charging: bool
    led_mode: int


class ProtocolKnowledgeError(ValueError):
    """A passive frame or sourced semantic value violates its known grammar."""


_OBSERVED_POLLING_CODEC = CodecSpec(
    CodecKind.RECIPROCAL, base=1000, allowed_raw_values=(1, 2, 4, 8)
)


def encode_redragon_m724_dpi(dpi: int) -> RedragonDpiEncoding:
    """Encode the observed M724 numeric formula without granting write authority."""

    if dpi <= 0:
        raise ProtocolKnowledgeError("DPI must be positive")
    raw = (dpi * 9 + 200) // 400
    if raw > 510:
        raise ProtocolKnowledgeError("DPI exceeds the observed one-range-bit representation")
    if raw > 255:
        return RedragonDpiEncoding((raw + 1) // 2, 1)
    return RedragonDpiEncoding(raw, 0)


def decode_redragon_m724_dpi(value: int, range_flag: int) -> int:
    """Decode the nominal M724 formula as an approximate integer DPI value."""

    if not 0 <= value <= 0xFF or range_flag not in (0, 1):
        raise ProtocolKnowledgeError("invalid M724 DPI value or range flag")
    numerator = value * (2 if range_flag else 1) * 400
    return (numerator + 4) // 9


def decode_ryunix_telemetry(report: bytes) -> RyunixTelemetry:
    """Decode one exact seven-byte numbered Kyu Pro MX1 telemetry report."""

    if len(report) != 7 or report[0] != 0x04:
        raise ProtocolKnowledgeError("not an exact Ryunix telemetry report")
    active, stage, polling, battery, charging, led_mode = report[1:]
    if active not in (0, 1):
        raise ProtocolKnowledgeError("invalid Ryunix active flag")
    if charging not in (0, 1):
        raise ProtocolKnowledgeError("invalid Ryunix charging flag")
    if battery > 100:
        raise ProtocolKnowledgeError("invalid Ryunix battery percentage")
    try:
        polling_rate_hz = decode_value(polling, _OBSERVED_POLLING_CODEC)
    except ProtocolCodecError as exc:
        raise ProtocolKnowledgeError("invalid Ryunix polling code") from exc
    return RyunixTelemetry(
        bool(active), stage, polling_rate_hz, battery, bool(charging), led_mode
    )


def _source(
    project: str,
    reference: str,
    trust: SourceTrust,
    *,
    verified_on: str | None = None,
    verified_date: str | None = None,
    notes: str = "",
) -> ProtocolSource:
    return ProtocolSource(
        project=project,
        reference=reference,
        trust=trust,
        verified_on=verified_on,
        verified_date=verified_date,
        notes=notes,
    )


# The initial repertoire deliberately records only facts we can explain and
# source.  Families with older or incomplete write verification are useful for
# classification but remain write-disabled until mouse-control proves them on
# hardware or a modern upstream verification justifies promotion.
DEFAULT_REPERTOIRE: tuple[ProtocolFamily, ...] = (
    ProtocolFamily(
        name="bitmouse-72",
        revision="semantic-frame-v1",
        sources=(
            _source(
                "source-derived semantic fixture",
                "BITMOUSE 0x72 asymmetric request/reply grammar",
                SourceTrust.REFERENCE,
                notes="Independently expressed recognition facts; no runtime recipe or hardware qualification.",
            ),
        ),
        signatures=(
            ReportSignature("output", 0x72, exact_length=64, vendor_usage_required=True, weight=6),
            ReportSignature("input", 0x72, exact_length=64, vendor_usage_required=True, weight=6),
        ),
        recognition=RecognitionRecipe(
            discriminators=(
                SemanticDiscriminator(
                    "request-frame-length", DiscriminatorKind.FRAME_LENGTH,
                    EvidenceCategory.FRAME, FrameSide.REQUEST, expected=64,
                ),
                SemanticDiscriminator(
                    "response-frame-length", DiscriminatorKind.FRAME_LENGTH,
                    EvidenceCategory.FRAME, FrameSide.RESPONSE, expected=64,
                ),
                SemanticDiscriminator(
                    "request-report-marker", DiscriminatorKind.BYTE_EQUALS,
                    EvidenceCategory.FRAME, FrameSide.REQUEST, offset=1, expected=0x72,
                ),
                SemanticDiscriminator(
                    "response-report-marker", DiscriminatorKind.BYTE_EQUALS,
                    EvidenceCategory.FRAME, FrameSide.RESPONSE, offset=0, expected=0x72,
                ),
                SemanticDiscriminator(
                    "leading-request-checksum", DiscriminatorKind.SUM8_EQUALS,
                    EvidenceCategory.INTEGRITY, FrameSide.REQUEST, offset=0, start=1, end=6,
                ),
                SemanticDiscriminator(
                    "target-correlation", DiscriminatorKind.FIELD_EQUALS,
                    EvidenceCategory.RELATIONSHIP, FrameSide.RESPONSE, offset=1,
                    other_side=FrameSide.REQUEST, other_offset=2,
                ),
                SemanticDiscriminator(
                    "sequence-correlation", DiscriminatorKind.FIELD_EQUALS,
                    EvidenceCategory.RELATIONSHIP, FrameSide.RESPONSE, offset=2,
                    other_side=FrameSide.REQUEST, other_offset=3,
                ),
                SemanticDiscriminator(
                    "declared-semantic-reply-length", DiscriminatorKind.DECLARED_LENGTH,
                    EvidenceCategory.RELATIONSHIP, FrameSide.RESPONSE, offset=4,
                    other_side=FrameSide.REQUEST, other_offset=5, payload_offset=5,
                ),
            ),
            minimum_independent_categories=3,
        ),
        transports=(TransportKind.HID_OUTPUT, TransportKind.HID_INPUT),
        write_scope=WriteScope.NEVER,
        minimum_match_score=12,
        notes="Structural compatibility requires semantic target/sequence/length discrimination.",
    ),
    ProtocolFamily(
        name="hidpp2",
        revision="dynamic-root",
        sources=(
            _source(
                "mouse-control",
                "G305 physical discovery acceptance",
                SourceTrust.LOCAL_PROVEN,
                verified_on="Logitech G305 LIGHTSPEED",
                verified_date="2026-09-15",
                notes="Dynamic ROOT discovery proved DPI/report-rate/battery semantics on hardware.",
            ),
        ),
        vendor_ids=(0x046D,),
        transports=(TransportKind.BACKEND, TransportKind.HID_INPUT),
        write_scope=WriteScope.BACKEND_ONLY,
        minimum_match_score=999,
        notes="Known HID++ remains a teacher/execution backend; VID alone is never a generic match.",
    ),
    ProtocolFamily(
        name="razer-rpc90",
        revision="classic-90-byte",
        sources=(
            _source(
                "OpenRazer",
                "driver/razercommon.h",
                SourceTrust.MAINTAINED,
                notes="90-byte status/transaction/class/command/payload/XOR envelope.",
            ),
            _source(
                "OpenRazer",
                "PR #2886 — Viper V3 Pro SE",
                SourceTrust.HARDWARE_VERIFIED,
                verified_on="Razer Viper V3 Pro SE wired + wireless",
                verified_date="2026-08",
                notes="Physical hardware confirmed DPI, poll rate, battery and hot-plug behavior.",
            ),
        ),
        vendor_ids=(0x1532,),
        transports=(TransportKind.USB_CONTROL, TransportKind.BACKEND),
        write_scope=WriteScope.BACKEND_ONLY,
        minimum_match_score=999,
        notes="Command-specific transaction IDs/quirks make backend execution safer than family inference.",
    ),
    ProtocolFamily(
        name="asus-rog-command64",
        revision="omni-v2",
        sources=(
            _source(
                "libratbag",
                "commit d93a8bc47496129f11b544aa5ea46f9d269c6bab",
                SourceTrust.HARDWARE_VERIFIED,
                verified_on="ASUS ROG Strix Impact III Wireless via Omni receiver",
                verified_date="2026-08-18",
                notes="Identification, DPI, report rate and settings writes round-tripped and survived restart.",
            ),
        ),
        vendor_ids=(0x0B05,),
        transports=(TransportKind.HID_OUTPUT, TransportKind.HID_INPUT),
        write_scope=WriteScope.EXACT_MODEL,
        minimum_match_score=999,
        notes="Shared receiver identity must be resolved by protocol signature, not USB PID alone.",
    ),
    ProtocolFamily(
        name="steelseries-direct-command",
        revision="multi-generation",
        sources=(
            _source(
                "rivalcfg",
                "rivalcfg/devices/aerox5.py",
                SourceTrust.MAINTAINED,
                notes="Declarative OUTPUT-report commands for DPI, polling, buttons and save.",
            ),
            _source(
                "rivalcfg",
                "PR #288 — Rival 650 lift-off distance",
                SourceTrust.HARDWARE_VERIFIED,
                verified_on="SteelSeries Rival 650 wired + wireless dongle",
                verified_date="2026-08",
                notes="Positions verified physically; persistent setting survived power cycle.",
            ),
        ),
        vendor_ids=(0x1038,),
        transports=(TransportKind.HID_OUTPUT, TransportKind.HID_INPUT),
        write_scope=WriteScope.EXACT_MODEL,
        minimum_match_score=999,
        notes="SteelSeries has multiple protocol generations; revision must be resolved before writes.",
    ),
    ProtocolFamily(
        name="sinowealth-config-blob",
        revision="classic",
        sources=(
            _source(
                "libratbag",
                "src/driver-sinowealth.c",
                SourceTrust.MAINTAINED,
                notes="Shared ODM configuration-blob protocol across Glorious/G-Wolves and sensor variants.",
            ),
        ),
        signatures=(
            ReportSignature("feature", 0x04, exact_length=520, vendor_usage_required=True, weight=7),
            ReportSignature("feature", 0x05, exact_length=6, vendor_usage_required=True, weight=7),
        ),
        transports=(TransportKind.HID_FEATURE_GET, TransportKind.HID_FEATURE_SET),
        bindings=(
            FieldBinding(
                SemanticBehavior.REPORT_RATE_HZ,
                "configuration",
                10,
                codec=CodecSpec(
                    CodecKind.ENUM,
                    values={0x01: 125, 0x02: 250, 0x03: 500, 0x04: 1000},
                ),
                evidence_note="Offset varies by layout; binding is descriptive, not write-authorizing.",
            ),
        ),
        write_scope=WriteScope.NEVER,
        minimum_match_score=14,
        notes="Strong report-shape fingerprint; writes stay disabled until modern hardware verification is imported.",
    ),
    ProtocolFamily(
        name="attackshark-x11-feature",
        revision="x11",
        sources=(
            _source(
                "OpenSharkX11",
                "docs/protocol/PROTOCOL_EN.md",
                SourceTrust.HARDWARE_VERIFIED,
                verified_on="Attack Shark X11 wired + 2.4 GHz",
                verified_date="2026",
                notes="DPI, polling, events, prerequisites and dangerous report 0x0b documented from hardware tests.",
            ),
            _source(
                "OpenMouse mouse-protocol",
                "commit eba2e832be60b361cdfbc95d7d51ab47b9522e97",
                SourceTrust.MAINTAINED,
                verified_date="2026-09-14",
                notes="Native X11 polling, DPI and battery integration merged into the maintained protocol package.",
            ),
        ),
        signatures=(
            ReportSignature("feature", 0x04, minimum_length=52, maximum_length=56, weight=6),
            ReportSignature("feature", 0x05, exact_length=15, weight=5),
            ReportSignature("feature", 0x06, exact_length=9, weight=6),
        ),
        vendor_ids=(0x1D57,),
        product_ids=(0xFA55, 0xFA60),
        transports=(TransportKind.HID_FEATURE_SET, TransportKind.USB_INTERRUPT),
        bindings=(
            FieldBinding(
                SemanticBehavior.DPI_STAGE_INDEX,
                "dpi_config",
                24,
                codec=CodecSpec(CodecKind.LINEAR, scale=1, offset=-1),
            ),
            FieldBinding(
                SemanticBehavior.REPORT_RATE_HZ,
                "polling",
                3,
                codec=CodecSpec(
                    CodecKind.ENUM,
                    values={0x08: 125, 0x04: 250, 0x02: 500, 0x01: 1000},
                ),
            ),
            FieldBinding(
                SemanticBehavior.BATTERY_PERCENT,
                "event_battery",
                4,
                codec=CodecSpec(CodecKind.U8),
            ),
        ),
        write_scope=WriteScope.EXACT_MODEL,
        minimum_match_score=12,
        notes="Report 0x0b is known dangerous and must never be generated by discovery.",
    ),
    ProtocolFamily(
        name="ajazz-aj-feature64",
        revision="aj-series",
        sources=(
            _source(
                "ajazz-control-center",
                "docs/protocols/mouse/aj_series.md",
                SourceTrust.HARDWARE_VERIFIED,
                verified_on="AJAZZ 2.4G/8K AJ-series hardware",
                verified_date="2026-05-22",
                notes="Shipping-firmware battery flow verified: 0xF7 status poll + delayed GET_FEATURE.",
            ),
        ),
        signatures=(
            ReportSignature(
                "feature",
                0x05,
                exact_length=64,
                vendor_usage_required=True,
                weight=8,
            ),
        ),
        transports=(TransportKind.HID_FEATURE_GET, TransportKind.HID_FEATURE_SET),
        write_scope=WriteScope.EXACT_MODEL,
        minimum_match_score=8,
        notes="64-byte command/subcommand/length/SUM8 envelope; battery uses a separate heartbeat transaction.",
    ),
    ProtocolFamily(
        name="holtek-venus-feature-flash",
        revision="fc55-research-v1",
        sources=(
            _source(
                "Mouse Control research corpus",
                "DISCOVERY 90%+ research payload — Holtek Venus",
                SourceTrust.REFERENCE,
                notes="Project-owned declarative facts only; no upstream capture or executable write recipe imported.",
            ),
        ),
        signatures=(
            ReportSignature(
                "feature", 0x02, exact_length=16,
                required_usage_page=0xFFA0,
                required_interface_number=2,
                weight=8,
            ),
            ReportSignature(
                "feature", 0x03, exact_length=64,
                required_usage_page=0xFFA0,
                required_interface_number=2,
                weight=8,
            ),
        ),
        vendor_ids=(0x04D9,),
        product_ids=(0xFC55,),
        transports=(TransportKind.HID_FEATURE_GET, TransportKind.HID_FEATURE_SET),
        bindings=(
            FieldBinding(
                SemanticBehavior.REPORT_RATE_HZ,
                "polling-representation",
                0,
                codec=_OBSERVED_POLLING_CODEC,
                evidence_note="Representation only; command location and write semantics remain unresolved.",
            ),
        ),
        write_scope=WriteScope.NEVER,
        identity_required=True,
        minimum_match_score=19,
        notes=(
            "F1 control, F2 read, F3 flash-data and F5 status/control are vocabulary facts. "
            "Flash write, category commit and possible reset/re-enumeration are descriptive dialogue facts; "
            "storage and physical effect remain separate and all writes are disabled."
        ),
    ),
    ProtocolFamily(
        name="keychron-m6-paired-namespaces",
        revision="ffc1-research-v1",
        sources=(
            _source(
                "Mouse Control research corpus",
                "DISCOVERY 90%+ research payload — Keychron M6",
                SourceTrust.REFERENCE,
                notes="Project-owned structural fixture; semantic offsets and write packets were not imported.",
            ),
        ),
        signatures=(
            ReportSignature("output", 0xB3, required_usage_page=0xFFC1, weight=6),
            ReportSignature("input", 0xB4, required_usage_page=0xFFC1, weight=6),
            ReportSignature("output", 0xB5, required_usage_page=0xFFC1, weight=6),
            ReportSignature("input", 0xB6, required_usage_page=0xFFC1, weight=6),
        ),
        recognition=RecognitionRecipe(
            discriminators=(
                SemanticDiscriminator(
                    "query-response-namespace-pair",
                    DiscriminatorKind.REPORT_ID_PAIR,
                    EvidenceCategory.DIALOGUE,
                    request_report_id=0xB3,
                    response_report_id=0xB4,
                    match_all_exchanges=False,
                ),
                SemanticDiscriminator(
                    "setting-ack-namespace-pair",
                    DiscriminatorKind.REPORT_ID_PAIR,
                    EvidenceCategory.DIALOGUE,
                    request_report_id=0xB5,
                    response_report_id=0xB6,
                    match_all_exchanges=False,
                ),
            ),
            minimum_independent_categories=3,
        ),
        transports=(TransportKind.HID_OUTPUT, TransportKind.HID_INPUT),
        write_scope=WriteScope.NEVER,
        minimum_match_score=24,
        notes=(
            "B3→B4 is the query/status namespace and B5→B6 is the setting/ACK namespace. "
            "The structural collision remains only a candidate until captured dialogue proves those pairings; "
            "five LE16 DPI stages and dynamic report-rate capabilities are descriptive facts only."
        ),
    ),
    ProtocolFamily(
        name="redragon-m724-feature-session",
        revision="m724-k1ng-1k-v1",
        sources=(
            _source(
                "OpenMouse mouse-protocol",
                "commit b7183b395b2b0350c1e50cbcd9616c56f8de2e7a; docs/redragon-m724-testing.md",
                SourceTrust.MAINTAINED,
                verified_date="2026-09-18",
                notes="Feature-report session, DPI, polling and commit grammar; independently re-expressed as facts.",
            ),
            _source(
                "OpenMouse mouse-protocol",
                "commit 73f57898340636e0a0fdab8ce8f517449e065e33",
                SourceTrust.HARDWARE_VERIFIED,
                verified_on="Redragon M724 K1NG 1K wired (04d9:fc7a)",
                verified_date="2026-09-18",
                notes="Upstream physically verified DPI/polling writes and the safety-critical session close requirement.",
            ),
        ),
        signatures=(
            ReportSignature(
                "feature", 0x02, exact_length=16,
                required_usage_page=0xFFA0,
                required_application_usage=(0xFFA0, 0x01),
                weight=8,
            ),
            ReportSignature("feature", 0x03, required=False, weight=1),
            ReportSignature("feature", 0x04, required=False, weight=1),
            ReportSignature("feature", 0x05, required=False, weight=1),
            ReportSignature("feature", 0x06, required=False, weight=1),
        ),
        vendor_ids=(0x04D9,),
        product_ids=(0xFC7A,),
        transports=(TransportKind.HID_FEATURE_GET, TransportKind.HID_FEATURE_SET),
        bindings=(
            FieldBinding(
                SemanticBehavior.REPORT_RATE_HZ,
                "polling-config-02-f3-32-00-06",
                8,
                codec=_OBSERVED_POLLING_CODEC,
                evidence_note="Observed raw domain is exactly 01/02/04/08; descriptive only.",
            ),
        ),
        sessions=(
            SessionGrammar(
                name="feature-report-configuration",
                transport=TransportKind.HID_FEATURE_SET,
                open_frame=bytes((0x02, 0xF5, 0x00) + (0,) * 13),
                close_frame=bytes((0x02, 0xF5, 0x01) + (0,) * 13),
                write_prefix=b"\x02\xf3",
                commit_codes=(0x04, 0x01, 0x02, 0x08, 0x10),
                cleanup_required=True,
                abandoned_session_hazard="Interface may stall until physical reconnect",
                unresolved_semantics=(
                    "individual commit-code meanings",
                    "active DPI-stage read/selection",
                    "button configuration",
                    "LED configuration",
                    "profile selection",
                    "full report-3 command",
                ),
            ),
        ),
        write_scope=WriteScope.NEVER,
        identity_required=True,
        minimum_match_score=11,
        notes=(
            "Exact M724 structural research only. Report 2 is descriptor-sized as a 16-byte numbered frame; "
            "other reports may declare oversized lengths while meaningful replies remain short. DPI table uses "
            "section 05, profile 00, subcommands 44/4a/50/56/5c and paired X/Y values. FA FA is a responder marker, "
            "not semantic readback. No executable write recipe is exposed because guaranteed cleanup and local "
            "physical proof are absent."
        ),
    ),
    ProtocolFamily(
        name="ryunix-kyu-pro-mx1-telemetry",
        revision="telemetry-v1",
        sources=(
            _source(
                "OpenMouse mouse-protocol",
                "commit 37739057a4b1a5484d8e131f1a6b47d753cad7ce; src/ryunix/kyu-pro-mx1.ts",
                SourceTrust.MAINTAINED,
                verified_on="Ryunix Kyu Pro MX1 wired/wireless identities",
                verified_date="2026-09-18",
                notes="Six-byte passive telemetry semantics; no configuration-write authority imported.",
            ),
        ),
        signatures=(
            ReportSignature(
                "input", 0x04, exact_length=7,
                required_usage_page=0x0A,
                required_application_usage=(0x0A, 0xC7),
                weight=8,
            ),
            ReportSignature("feature", 0x05, required=False, weight=1),
        ),
        vendor_ids=(0x04F3,),
        product_ids=(0x026E, 0x026F),
        transports=(TransportKind.HID_INPUT,),
        bindings=(
            FieldBinding(SemanticBehavior.ACTIVE_STATE, "telemetry", 1),
            FieldBinding(SemanticBehavior.DPI_STAGE_INDEX, "telemetry", 2),
            FieldBinding(
                SemanticBehavior.REPORT_RATE_HZ, "telemetry", 3,
                codec=_OBSERVED_POLLING_CODEC,
            ),
            FieldBinding(SemanticBehavior.BATTERY_PERCENT, "telemetry", 4),
            FieldBinding(SemanticBehavior.CHARGING_STATE, "telemetry", 5),
            FieldBinding(
                SemanticBehavior.LED_MODE, "telemetry", 6,
                evidence_note="Classification only; Mouse Control does not manage RGB.",
            ),
        ),
        write_scope=WriteScope.NEVER,
        identity_required=True,
        minimum_match_score=11,
        notes="Read-only telemetry knowledge. Report 05 existence never implies configuration authority.",
    ),
    ProtocolFamily(
        name="mchose-v3-block-rpc",
        revision="a7-v3",
        sources=(
            _source(
                "OpenMouse mouse-protocol",
                "commit 5b0b2a93719158182176253da4c3574d47981212",
                SourceTrust.MAINTAINED,
                verified_date="2026-09-12",
                notes="Read-modify-write block grammar documented, but commit explicitly states writes were not sent to hardware.",
            ),
            _source(
                "OpenMouse mouse-protocol",
                "commit a92e865687479f2578e57e0b6d852c06570abd82",
                SourceTrust.MAINTAINED,
                verified_date="2026-09-12",
                notes="Fresh cable/receiver captures established delayed replies, refusal replies and retry semantics.",
            ),
        ),
        transports=(TransportKind.HID_FEATURE_GET, TransportKind.HID_FEATURE_SET),
        write_scope=WriteScope.NEVER,
        minimum_match_score=999,
        notes="Useful transaction-state-machine teacher; writes intentionally remain untrusted.",
    ),
)


def recognize_family_semantics(
    candidate: FamilyCandidate,
    exchanges: Iterable[SemanticExchange],
) -> SemanticFamilyRecognition:
    """Evaluate one family's data-only recipe against passive exchanges."""

    recipe = candidate.family.recognition
    if recipe is None:
        return SemanticFamilyRecognition(
            candidate, (), ("no-safe-semantic-discriminator",), (), ()
        )
    observed = tuple(exchanges)
    if not observed:
        return SemanticFamilyRecognition(
            candidate, (), ("passive-request-response-exchange",), (), ()
        )

    matched: list[str] = []
    missing: list[str] = []
    categories: set[EvidenceCategory] = set()
    if candidate.family.signatures:
        categories.add(EvidenceCategory.FRAME)
    if candidate.exact_identity:
        categories.add(EvidenceCategory.IDENTITY)
    if any(
        signature.required_usage_page is not None
        or signature.required_application_usage is not None
        or signature.required_interface_number is not None
        for signature in candidate.family.signatures
    ):
        categories.add(EvidenceCategory.TOPOLOGY)
    for discriminator in recipe.discriminators:
        results = tuple(
            _discriminator_matches(discriminator, exchange) for exchange in observed
        )
        passed = all(results) if discriminator.match_all_exchanges else any(results)
        if passed:
            matched.append(discriminator.name)
            categories.add(discriminator.category)
        else:
            missing.append(discriminator.name)

    records: list[bytes] = []
    length_rules = tuple(
        item for item in recipe.discriminators
        if item.kind is DiscriminatorKind.DECLARED_LENGTH and item.name in matched
    )
    if not missing and length_rules:
        rule = length_rules[0]
        for exchange in observed:
            frame = _frame(exchange, rule.side)
            declared = _field(frame, rule.offset, rule.width)
            records.append(frame[:rule.payload_offset + declared])

    return SemanticFamilyRecognition(
        candidate,
        tuple(sorted(matched)),
        tuple(sorted(missing)),
        tuple(records),
        tuple(sorted(categories, key=lambda item: item.value)),
    )


def _frame(exchange: SemanticExchange, side: FrameSide) -> bytes:
    return exchange.request if side is FrameSide.REQUEST else exchange.response


def _field(frame: bytes, offset: int, width: int) -> int:
    end = offset + width
    if end > len(frame):
        raise ProtocolKnowledgeError("semantic discriminator exceeds frame bounds")
    return int.from_bytes(frame[offset:end], "little")


def _discriminator_matches(
    discriminator: SemanticDiscriminator,
    exchange: SemanticExchange,
) -> bool:
    try:
        frame = _frame(exchange, discriminator.side)
        if discriminator.kind is DiscriminatorKind.FRAME_LENGTH:
            return len(frame) == discriminator.expected
        if discriminator.kind is DiscriminatorKind.BYTE_EQUALS:
            return _field(frame, discriminator.offset, discriminator.width) == discriminator.expected
        if discriminator.kind is DiscriminatorKind.FIELD_EQUALS:
            if discriminator.other_side is None:
                return False
            return _field(frame, discriminator.offset, discriminator.width) == _field(
                _frame(exchange, discriminator.other_side),
                discriminator.other_offset,
                discriminator.width,
            )
        if discriminator.kind is DiscriminatorKind.SUM8_EQUALS:
            end = len(frame) if discriminator.end is None else discriminator.end
            if end > len(frame):
                return False
            return _field(frame, discriminator.offset, discriminator.width) == (sum(frame[discriminator.start:end]) & 0xFF)
        if discriminator.kind is DiscriminatorKind.DECLARED_LENGTH:
            if discriminator.other_side is None:
                return False
            declared = _field(frame, discriminator.offset, discriminator.width)
            expected = _field(
                _frame(exchange, discriminator.other_side),
                discriminator.other_offset,
                discriminator.width,
            )
            return declared == expected and discriminator.payload_offset + declared <= len(frame)
        if discriminator.kind is DiscriminatorKind.REPORT_ID_PAIR:
            return (
                exchange.request_report_id == discriminator.request_report_id
                and exchange.response_report_id == discriminator.response_report_id
            )
    except ProtocolKnowledgeError:
        return False
    return False


def recognize_open_set(
    physical: PhysicalDevice,
    descriptors: Mapping[DeviceNode, ParsedHidDescriptor],
    *,
    exchanges: Mapping[str, Iterable[SemanticExchange]] | None = None,
    families: Iterable[ProtocolFamily] = DEFAULT_REPERTOIRE,
    minimum_margin: int = 3,
) -> OpenSetRecognition:
    """Recognize conservatively while preserving UNKNOWN and AMBIGUOUS states."""

    if minimum_margin < 0:
        raise ValueError("minimum_margin cannot be negative")
    structural = match_repertoire(physical, descriptors, families=families)
    if not structural:
        return OpenSetRecognition(RecognitionStatus.UNKNOWN, None, (), "no structural candidate")

    supplied = exchanges or {}
    evaluated = tuple(
        recognize_family_semantics(candidate, supplied.get(candidate.family.name, ()))
        for candidate in structural
    )

    def score(item: SemanticFamilyRecognition) -> int:
        weights = {
            discriminator.name: discriminator.weight
            for discriminator in (item.candidate.family.recognition.discriminators
                                  if item.candidate.family.recognition else ())
        }
        return item.candidate.score + sum(weights.get(name, 0) for name in item.matched)

    ranked = tuple(sorted(evaluated, key=lambda item: (-score(item), item.candidate.family.name)))
    recognized = tuple(item for item in ranked if item.recognized)
    if not recognized:
        if len(ranked) == 1:
            return OpenSetRecognition(
                RecognitionStatus.CANDIDATE, ranked[0].candidate.family.name, ranked,
                "structural evidence requires semantic confirmation",
            )
        return OpenSetRecognition(
            RecognitionStatus.AMBIGUOUS, None, ranked,
            "multiple structural candidates remain unresolved",
        )

    winner = recognized[0]
    runner_score = score(ranked[1]) if len(ranked) > 1 else -1
    if len(recognized) > 1 or score(winner) - runner_score < minimum_margin:
        return OpenSetRecognition(
            RecognitionStatus.AMBIGUOUS, None, ranked,
            "recognized candidate lacks the required margin",
        )
    return OpenSetRecognition(
        RecognitionStatus.RECOGNIZED, winner.candidate.family.name, ranked,
        "required independent semantic discriminators passed",
    )


def observed_reports(
    descriptors: Mapping[DeviceNode, ParsedHidDescriptor],
) -> tuple[ObservedReport, ...]:
    result: list[ObservedReport] = []
    for node, descriptor in descriptors.items():
        for report in descriptor.reports:
            result.append(
                ObservedReport(
                    node=node,
                    report_type=report.report_type,
                    report_id=report.report_id,
                    byte_length=report.byte_length,
                    vendor_usage=any(0xFF00 <= page <= 0xFFFF for page in report.usage_pages),
                    usage_pages=report.usage_pages,
                    application_usages=report.application_usages,
                    interface_number=node.interface_number,
                )
            )
    return tuple(result)


def _signature_matches(signature: ReportSignature, report: ObservedReport) -> bool:
    if signature.report_type != report.report_type:
        return False
    if signature.report_id is not None and signature.report_id != report.report_id:
        return False
    if signature.exact_length is not None and signature.exact_length != report.byte_length:
        return False
    if signature.minimum_length is not None and report.byte_length < signature.minimum_length:
        return False
    if signature.maximum_length is not None and report.byte_length > signature.maximum_length:
        return False
    if (
        signature.vendor_usage_required is not None
        and signature.vendor_usage_required != report.vendor_usage
    ):
        return False
    if (
        signature.required_usage_page is not None
        and signature.required_usage_page not in report.usage_pages
    ):
        return False
    if (
        signature.required_application_usage is not None
        and signature.required_application_usage not in report.application_usages
    ):
        return False
    if (
        signature.required_interface_number is not None
        and signature.required_interface_number != report.interface_number
    ):
        return False
    return True


def match_repertoire(
    physical: PhysicalDevice,
    descriptors: Mapping[DeviceNode, ParsedHidDescriptor],
    *,
    families: Iterable[ProtocolFamily] = DEFAULT_REPERTOIRE,
) -> tuple[FamilyCandidate, ...]:
    """Return structural protocol-family candidates ordered by evidence score."""

    reports = observed_reports(descriptors)
    candidates: list[FamilyCandidate] = []
    for family in families:
        score = 0
        matched: list[str] = []
        missing: list[str] = []
        rejected = False

        for signature in family.signatures:
            found = any(_signature_matches(signature, report) for report in reports)
            text = (
                f"{signature.report_type}:id="
                f"{('*' if signature.report_id is None else hex(signature.report_id))}"
            )
            if found:
                score += signature.weight
                matched.append(text)
            elif signature.required:
                missing.append(text)
                rejected = True
            else:
                missing.append(text)

        vendor_match = bool(
            family.vendor_ids
            and physical.vendor_id is not None
            and physical.vendor_id in family.vendor_ids
        )
        product_match = bool(
            family.product_ids
            and physical.product_id is not None
            and physical.product_id in family.product_ids
        )
        if vendor_match:
            score += 1
            matched.append("vendor-hint")
        if product_match:
            score += 2
            matched.append("product-hint")

        if family.identity_required and not (vendor_match and product_match):
            continue

        # Identity hints alone are intentionally insufficient for generic
        # repertoire matching.  Families without structural signatures are
        # teachers/backends until a stronger grammar signature is added.
        if rejected or score < family.minimum_match_score:
            continue

        exact_identity = product_match and (vendor_match or not family.vendor_ids)
        candidates.append(
            FamilyCandidate(
                family=family,
                score=score,
                matched=tuple(matched),
                missing=tuple(missing),
                exact_identity=exact_identity,
            )
        )

    return tuple(sorted(candidates, key=lambda item: (-item.score, item.family.name)))
