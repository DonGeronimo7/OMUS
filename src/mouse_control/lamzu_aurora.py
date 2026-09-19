"""Read-only LAMZU Aurora protocol-family knowledge.

Facts in this module are independently expressed from the vendor application
research package.  They are vendor evidence, not physical proof, and this
module contains no HID session, write transport, or runtime backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .protocol_grammar import (
    AsyncEventRecipe,
    CodecKind,
    CodecSpec,
    DangerousOperation,
    DeviceIdentityRecord,
    DeviceIdentityRole,
    DiscriminatorKind,
    EvidenceCategory,
    FieldBinding,
    FrameSide,
    ProtocolFamily,
    ProtocolFrameGrammar,
    ProtocolOperation,
    ProtocolSource,
    RecognitionRecipe,
    ReportSignature,
    SafetyClass,
    SemanticBehavior,
    SemanticDiscriminator,
    SourceTrust,
    StateDependencyRule,
    StatusTimingPolicy,
    TransportKind,
    WriteScope,
)
from .temporal_dialogue import (
    DialogueKind, DialogueObservation,
    PushedStateAssociation,
    PushedStateRecord,
    StateFreshness,
)


class AuroraKnowledgeError(ValueError):
    """Vendor knowledge cannot safely decode or represent the supplied value."""


class AuroraStatusAction(str, Enum):
    COMPLETE = "complete"
    POLL_RECEIVE = "poll_receive"
    RESEND = "bounded_resend"


@dataclass(frozen=True)
class AuroraNormalizedResponse:
    alignment: int
    status: int
    target: int
    logical_length: int
    page: int
    command: int
    payload: bytes
    canonical_frame: bytes


@dataclass(frozen=True)
class AuroraSensorModel:
    code: int
    name: str
    lod_options_tenths_mm: tuple[int, ...]
    dpi_max: int
    dpi_increment: int
    fine_lod: bool
    vendor_evidence: str = "vendor_implemented"


@dataclass(frozen=True)
class AuroraEvent:
    event_id: int
    name: str
    values: Mapping[str, int | bool | str]
    raw: bytes


@dataclass(frozen=True)
class AuroraBatteryState:
    percent: int
    charging: bool


@dataclass(frozen=True)
class AuroraRoutedIdentity:
    vendor_id: int
    product_id: int


_VENDOR_SOURCE = ProtocolSource(
    project="LAMZU Aurora",
    reference="Aurora 1.0.32 web application research package (2026-09-18)",
    trust=SourceTrust.VENDOR_IMPLEMENTED,
    verified_date="2026-09-18",
    notes=(
        "Structured paraphrase of vendor catalog and implementation behavior; "
        "not physical proof and never write authority."
    ),
)


def _model(
    model: str,
    product: int,
    connection: str,
    role: DeviceIdentityRole,
    *,
    capabilities: tuple[tuple[str, object], ...] = (),
    notes: str = "",
) -> DeviceIdentityRecord:
    return DeviceIdentityRecord(
        model, 0x37B0, product, connection, role, capabilities,
        "vendor_declared", notes,
    )


_THORN_54H20_CAPABILITIES = (
    ("maximum_dpi", 50000),
    ("dpi_stages", 5),
    ("polling_max_hz", 8000),
    ("xy_dpi", True),
    ("performance_selector", True),
    ("tracking_20k", True),
    ("angle_tune", True),
    ("scroll_bhop", True),
    ("sensor_model_query", True),
    ("receiver_indicator_slots", 3),
    ("protocol", "lamzu-aurora-feature64"),
)


AURORA_RECEIVER_INDICATOR_MEANINGS = {
    6: "battery",
    11: "dpi",
    10: "polling_rate",
    12: "signal",
}


AURORA_BUTTON_ACTIONS = (
    "disabled", "mouse_key", "dpi_switch", "scroll_left", "scroll_right",
    "fire_key", "shortcut", "macro", "report_rate_switch", "light_switch",
    "profile_switch", "dpi_lock", "scroll_up", "scroll_down",
)


LAMZU_MODELS: tuple[DeviceIdentityRecord, ...] = (
    _model("THORN", 0x0017, "wired", DeviceIdentityRole.MOUSE),
    _model("THORN", 0x0019, "wireless", DeviceIdentityRole.MOUSE),
    _model("THORN", 0x001B, "8k-receiver", DeviceIdentityRole.RECEIVER),
    _model("THORN", 0x0018, "bootloader", DeviceIdentityRole.BOOTLOADER),
    _model("THORN receiver", 0x0002, "bootloader", DeviceIdentityRole.BOOTLOADER),
    _model("THORN V2", 0x0021, "wired", DeviceIdentityRole.MOUSE),
    _model("THORN V2", 0x0003, "wireless", DeviceIdentityRole.MOUSE),
    _model("THORN V2", 0x0023, "8k-receiver", DeviceIdentityRole.RECEIVER),
    _model(
        "THORN V2 (54H20)", 0x0030, "wired-candidate", DeviceIdentityRole.MOUSE,
        capabilities=_THORN_54H20_CAPABILITIES,
    ),
    _model(
        "THORN V2 (54H20 / 3955)", 0x0040, "wired-candidate", DeviceIdentityRole.MOUSE,
        capabilities=_THORN_54H20_CAPABILITIES,
    ),
    _model(
        "THORN V2 (54H20)", 0x0032, "usb-8k-receiver", DeviceIdentityRole.RECEIVER,
        capabilities=_THORN_54H20_CAPABILITIES,
        notes="USB receiver identity; do not conflate with routed identity 002e.",
    ),
    _model(
        "THORN V2 (54H20)", 0x002E, "internal-8k-receiver",
        DeviceIdentityRole.INTERNAL_RECEIVER,
        capabilities=_THORN_54H20_CAPABILITIES,
        notes="Internal/alternate identity; physical relation to USB 0032 is unresolved.",
    ),
    _model("THORN V2 mouse", 0x0041, "bootloader", DeviceIdentityRole.BOOTLOADER),
    _model("THORN V2 receiver", 0x0033, "bootloader", DeviceIdentityRole.BOOTLOADER),
)


_DANGEROUS = (
    DangerousOperation("factory/default reset", "destructive device-wide state reset", 0x00, 0, 2),
    DangerousOperation("destructive profile reset", "destroys profile state", 0x0D, 0, 2),
    DangerousOperation("VID/PID write", "changes device identity", 0x10, 0, 0),
    DangerousOperation("descriptor/string write", "changes USB descriptors"),
    DangerousOperation("pairing operations", "changes receiver pairing ownership"),
    DangerousOperation("DFU/bootloader entry", "leaves normal application protocol"),
    DangerousOperation("flash erase", "irreversible storage destruction"),
    DangerousOperation("firmware programming", "firmware mutation"),
    DangerousOperation("firmware verification/program-control", "firmware control path"),
    DangerousOperation("arbitrary target enumeration", "unknown routed targets must not be scanned"),
    DangerousOperation("unknown command probing", "unknown commands have unknown side effects"),
)


def _operation(
    name: str,
    page: int,
    read: int | None,
    write: int | None,
    *,
    target: int = 0x02,
    length: int = 1,
    fields: tuple[str, ...] = (),
    prerequisite: tuple[str, ...] = (),
) -> ProtocolOperation:
    return ProtocolOperation(
        name, page, target, length, read, write,
        SafetyClass.READ_ONLY if write is None else SafetyClass.REVERSIBLE,
        fields, prerequisite, "vendor_implemented",
        automatic_experiment_allowed=False,
    )


_MODERN_OPERATIONS = (
    _operation("mouse firmware", 0, 0x81, None, length=16),
    _operation("dongle firmware", 0, 0x81, None, target=0, length=16),
    _operation("EID/device variant", 0, 0x82, None),
    _operation("battery/charging", 0, 0x83, None, length=2, fields=("charging", "percent")),
    _operation("active profile", 0, 0x85, 0x05, fields=("profile",)),
    _operation("sleep", 0, 0x87, 0x07, length=3, fields=("profile", "seconds_be16")),
    _operation("debounce", 0, 0x88, 0x08, length=2, fields=("profile", "milliseconds")),
    _operation("polling", 1, 0x80, 0x00, length=2, fields=("profile", "rate")),
    _operation("DPI stages", 1, 0x81, 0x01, length=2, fields=("profile", "xy_be16_pairs")),
    _operation("active DPI", 1, 0x82, 0x02, length=2, fields=("profile", "stage")),
    _operation("angle snapping", 1, 0x84, 0x04, length=2, fields=("profile", "enabled")),
    _operation("LOD", 1, 0x88, 0x08, length=2, fields=("profile", "encoded_lod")),
    _operation("Motion Sync", 1, 0x89, 0x09, length=2, fields=("profile", "enabled")),
    _operation("ripple control", 1, 0x8A, 0x0A, length=2, fields=("profile", "enabled")),
    _operation("High-Speed/Competition", 1, 0x8B, 0x0B, length=2, fields=("profile", "selector")),
    _operation("maximum DPI", 1, 0x8C, None, length=2, fields=("maximum_dpi_be16",)),
    _operation("X/Y DPI split", 1, 0x8D, 0x0D, length=2, fields=("profile", "enabled")),
    _operation("sensor model", 1, 0x8F, None, fields=("sensor_code",)),
    _operation(
        "Tracking/20K", 1, 0x93, 0x13, length=2,
        fields=("profile", "enabled"), prerequisite=("High-Speed/Competition",),
    ),
    _operation("Angle Tune", 1, 0x94, 0x14, length=2, fields=("profile", "signed_i8")),
    _operation("Scroll Bhop", 0, 0x99, 0x19, length=4, fields=("profile", "mode", "window_be16")),
    _operation("Rapid Trigger", 0, 0x9A, 0x1A, length=3, fields=("profile", "left", "right")),
    _operation("DPI indicator", 2, 0x84, 0x04),
    _operation("DPI stage colors", 2, 0x81, 0x01),
    _operation("receiver light/effect", 2, 0x80, 0x00),
    _operation("receiver lightness", 2, 0x82, 0x02),
    _operation("button actions", 3, 0x80, 0x00),
    _operation("button combinations", 3, 0x81, 0x01),
    ProtocolOperation(
        "macro allocate", 4, 0x02, 1, None, 0x01, SafetyClass.PERSISTENT,
        ("size_be",), (), "vendor_implemented", False,
    ),
    ProtocolOperation(
        "macro delete", 4, 0x02, 1, None, 0x02, SafetyClass.PERSISTENT,
        ("macro_id",), (), "vendor_implemented", False,
    ),
    ProtocolOperation(
        "macro data write", 4, 0x02, 1, None, 0x03, SafetyClass.PERSISTENT,
        ("address_be", "length_be", "data"), (), "vendor_implemented", False,
    ),
    _operation("macro size", 4, 0x81, None),
    _operation("macro data read", 4, 0x83, None),
    _operation("routed VID/PID", 0, 0x8B, None, target=1, length=6, fields=("argument_02", "vid_be16", "pid_be16")),
    _operation("USB PID", 0, 0x81, None, target=1, length=16, fields=("pid_be16",)),
)


_ASYNC_EVENTS = (
    AsyncEventRecipe("DPI", 0x01, 0x04, 0x04, (
        FieldBinding(SemanticBehavior.DPI_STAGE_INDEX, "event", 2),
        FieldBinding(SemanticBehavior.DPI_X, "event", 3, 2, CodecSpec(CodecKind.U16_BE)),
        FieldBinding(SemanticBehavior.DPI_Y, "event", 5, 2, CodecSpec(CodecKind.U16_BE)),
    )),
    AsyncEventRecipe("profile", 0x02, 0x04, 0x04, (), action="reread"),
    AsyncEventRecipe("battery/charging", 0x03, 0x04, 0x04, (
        FieldBinding(SemanticBehavior.BATTERY_PERCENT, "event", 2),
        FieldBinding(SemanticBehavior.CHARGING_STATE, "event", 3),
    )),
    AsyncEventRecipe("connection", 0x06, 0x04, 0x04, (
        FieldBinding(SemanticBehavior.CONNECTION_STATE, "event", 2),
    )),
    AsyncEventRecipe("LOD", 0x07, 0x04, 0x04, (
        FieldBinding(SemanticBehavior.LIFT_OFF_DISTANCE, "event", 2),
    )),
    AsyncEventRecipe("polling", 0x08, 0x04, 0x04, (
        FieldBinding(SemanticBehavior.REPORT_RATE_HZ, "event", 2),
    )),
    AsyncEventRecipe("performance", 0x0D, 0x04, 0x04, (
        FieldBinding(SemanticBehavior.PERFORMANCE_SELECTOR, "event", 2),
        FieldBinding(SemanticBehavior.TRACKING_20K, "event", 3),
    )),
)


LAMZU_AURORA_MODERN = ProtocolFamily(
    name="lamzu-aurora-feature64",
    revision="aurora-1.0.32-vendor-evidence",
    sources=(_VENDOR_SOURCE,),
    signatures=(
        ReportSignature("feature", 0x00, exact_length=64, vendor_usage_required=True, weight=8),
        ReportSignature("input", 0x04, minimum_length=4, maximum_length=64, vendor_usage_required=True, weight=6),
    ),
    vendor_ids=(0x373E, 0x37B0),
    # Paired VID:PID catalog records live in ``models``. ProtocolFamily's flat
    # product hint cannot safely express those pairs across both vendor IDs.
    product_ids=(),
    transports=(TransportKind.HID_FEATURE_GET, TransportKind.HID_FEATURE_SET, TransportKind.HID_INPUT),
    recognition=RecognitionRecipe((
        SemanticDiscriminator("request-frame-length", DiscriminatorKind.FRAME_LENGTH, EvidenceCategory.FRAME, FrameSide.REQUEST, expected=64),
        SemanticDiscriminator("response-frame-length", DiscriminatorKind.FRAME_LENGTH, EvidenceCategory.FRAME, FrameSide.RESPONSE, expected=64),
        SemanticDiscriminator("request-status-zero", DiscriminatorKind.BYTE_EQUALS, EvidenceCategory.FRAME, FrameSide.REQUEST, offset=0, expected=0),
        SemanticDiscriminator("request-reserved-zero", DiscriminatorKind.BYTE_EQUALS, EvidenceCategory.FRAME, FrameSide.REQUEST, offset=1, expected=0),
        SemanticDiscriminator("target-correlation", DiscriminatorKind.FIELD_EQUALS, EvidenceCategory.RELATIONSHIP, FrameSide.RESPONSE, offset=2, other_side=FrameSide.REQUEST, other_offset=2),
        SemanticDiscriminator("page-correlation", DiscriminatorKind.FIELD_EQUALS, EvidenceCategory.RELATIONSHIP, FrameSide.RESPONSE, offset=4, other_side=FrameSide.REQUEST, other_offset=4),
        SemanticDiscriminator("command-correlation", DiscriminatorKind.FIELD_EQUALS, EvidenceCategory.RELATIONSHIP, FrameSide.RESPONSE, offset=5, other_side=FrameSide.REQUEST, other_offset=5),
        SemanticDiscriminator("feature-report-zero-dialogue", DiscriminatorKind.REPORT_ID_PAIR, EvidenceCategory.DIALOGUE, request_report_id=0, response_report_id=0),
    ), minimum_independent_categories=3),
    frame_grammars=(ProtocolFrameGrammar(
        "aurora-current-control", "feature", 0, 64,
        status_offset=0, reserved_offset=1, target_offset=2, length_offset=3,
        page_offset=4, command_offset=5, payload_offset=6,
        response_alignment_offsets=(0, 1),
    ),),
    operations=_MODERN_OPERATIONS,
    async_events=_ASYNC_EVENTS,
    models=LAMZU_MODELS,
    dependencies=(StateDependencyRule(
        "High-Speed/Competition", "Tracking/20K", True, True,
        ("20K requires Competition Mode", "High-Speed conflicts with 2K/4K/8K polling"),
    ),),
    dangerous_operations=_DANGEROUS,
    status_timing=StatusTimingPolicy(
        (0xA1, 0x02), poll_below=0xA1, resend_above=0xA1,
        maximum_receive_polls=100, maximum_resends=3,
        delay_priors_ms=(15, 20, 30, 100),
        evidence_note="Vendor timing priors only; measured timing supersedes them.",
    ),
    write_scope=WriteScope.NEVER,
    minimum_match_score=14,
    notes=(
        "Vendor-described 64-byte Feature Report 0 family with sibling Input Report 4. "
        "All setters are descriptive only; exact-model operations require physical proof."
    ),
)


LAMZU_LEGACY_FLASH_SEMANTICS = (
    "polling", "dpi_stage_count", "active_dpi", "lod", "dpi_values",
    "dpi_colors", "button_functions", "debounce", "motion_sync", "sleep",
    "angle_snapping", "ripple_control", "performance_states", "shortcuts",
    "macros",
)


_LEGACY_OPERATIONS = (
    _operation("legacy battery", 0, 0x04, None, target=0, length=1),
    _operation("legacy firmware", 0, 0x12, None, target=0, length=1),
    _operation("legacy active profile", 0, 0x0E, 0x0F, target=0, length=1),
    _operation(
        "legacy flash read", 0, 0x08, None, target=0, length=1,
        fields=LAMZU_LEGACY_FLASH_SEMANTICS,
    ),
    ProtocolOperation(
        "legacy flash write", 0, 0, 1, None, 0x07, SafetyClass.PERSISTENT,
        ("address", "data", *LAMZU_LEGACY_FLASH_SEMANTICS),
        (), "vendor_implemented", False,
    ),
)


_LEGACY_DANGEROUS = _DANGEROUS + (
    DangerousOperation("legacy enter pair", "changes receiver pairing ownership", 0x05),
    DangerousOperation("legacy pairing state/control", "pairing workflow is not a Discovery experiment", 0x06),
    DangerousOperation("legacy clear setting", "destructive configuration reset", 0x09),
    DangerousOperation("legacy set VID/PID", "changes USB identity", 0x0B),
    DangerousOperation("legacy set descriptor", "changes USB descriptor strings", 0x0C),
    DangerousOperation("legacy USB update mode", "enters firmware update mode", 0x0D),
)


LAMZU_AURORA_LEGACY = ProtocolFamily(
    name="lamzu-legacy-report8",
    revision="aurora-1.0.32-vendor-evidence",
    sources=(_VENDOR_SOURCE,),
    signatures=(
        ReportSignature("output", 0x08, exact_length=16, vendor_usage_required=True, weight=6),
        ReportSignature("input", 0x08, exact_length=16, vendor_usage_required=True, weight=6),
    ),
    vendor_ids=(0x3554,),
    transports=(TransportKind.HID_OUTPUT, TransportKind.HID_INPUT),
    recognition=RecognitionRecipe((
        SemanticDiscriminator("legacy-request-length", DiscriminatorKind.FRAME_LENGTH, EvidenceCategory.FRAME, FrameSide.REQUEST, expected=16),
        SemanticDiscriminator("legacy-response-length", DiscriminatorKind.FRAME_LENGTH, EvidenceCategory.FRAME, FrameSide.RESPONSE, expected=16),
        SemanticDiscriminator("legacy-report8-dialogue", DiscriminatorKind.REPORT_ID_PAIR, EvidenceCategory.DIALOGUE, request_report_id=8, response_report_id=8),
        SemanticDiscriminator("legacy-request-checksum", DiscriminatorKind.SUM8_TOTAL_EQUALS, EvidenceCategory.INTEGRITY, FrameSide.REQUEST, offset=15, start=0, end=15, expected=0x4D),
    ), minimum_independent_categories=3),
    frame_grammars=(ProtocolFrameGrammar(
        "lamzu-legacy-report8", "output", 8, 16,
        command_offset=0, payload_offset=1, checksum="0x55 complement including report-id contribution",
    ),),
    operations=_LEGACY_OPERATIONS,
    dangerous_operations=_LEGACY_DANGEROUS,
    write_scope=WriteScope.NEVER,
    minimum_match_score=13,
    notes=(
        "Separate VID 3554 report-8 generation with flash-layout knowledge for polling, DPI, "
        "LOD, debounce, Motion Sync, sleep, angle, ripple, performance, buttons and macros."
    ),
)


LAMZU_AURORA_FAMILIES = (LAMZU_AURORA_MODERN, LAMZU_AURORA_LEGACY)


def lamzu_model(vendor_id: int, product_id: int) -> DeviceIdentityRecord | None:
    return next(
        (item for item in LAMZU_MODELS if item.vendor_id == vendor_id and item.product_id == product_id),
        None,
    )


def is_lamzu_bootloader_identity(vendor_id: int | None, product_id: int | None) -> bool:
    if vendor_id is None or product_id is None:
        return False
    model = lamzu_model(vendor_id, product_id)
    return model is not None and not model.configurable


def operation(name: str, *, legacy: bool = False) -> ProtocolOperation:
    family = LAMZU_AURORA_LEGACY if legacy else LAMZU_AURORA_MODERN
    try:
        return next(item for item in family.operations if item.name == name)
    except StopIteration as exc:
        raise AuroraKnowledgeError(f"unknown LAMZU operation {name!r}") from exc


def operation_is_automatic_experiment(name: str, *, legacy: bool = False) -> bool:
    return operation(name, legacy=legacy).automatic_experiment_allowed


def dangerous_operation_names() -> tuple[str, ...]:
    return tuple(item.name for item in _DANGEROUS)


def build_read_request(name: str, *, arguments: bytes = b"") -> bytes:
    """Encode one documented read fixture without executing or authorizing it."""

    recipe = operation(name)
    if recipe.read_command is None:
        raise AuroraKnowledgeError(f"{name} has no documented read operation")
    if len(arguments) > 58:
        raise AuroraKnowledgeError("Aurora arguments exceed the fixed report")
    frame = bytearray(64)
    frame[2] = recipe.target
    frame[3] = recipe.request_length
    frame[4] = recipe.page
    frame[5] = recipe.read_command
    frame[6:6 + len(arguments)] = arguments
    return bytes(frame)


def normalize_response(response: bytes, *, expected_command: int) -> AuroraNormalizedResponse:
    if len(response) not in (64, 65):
        raise AuroraKnowledgeError("Aurora response must be 64 bytes plus at most one alignment byte")
    alignments = tuple(
        alignment for alignment in (0, 1)
        if 5 + alignment < len(response) and response[5 + alignment] == expected_command
    )
    if len(alignments) != 1:
        raise AuroraKnowledgeError("response alignment is absent or ambiguous")
    alignment = alignments[0]
    aligned = response[alignment:alignment + 64]
    if len(aligned) < 7:
        raise AuroraKnowledgeError("aligned Aurora response is incomplete")
    canonical = aligned.ljust(64, b"\x00")
    logical_length = canonical[3]
    payload_end = min(len(canonical), 6 + logical_length)
    return AuroraNormalizedResponse(
        alignment, canonical[0], canonical[2], logical_length,
        canonical[4], canonical[5], canonical[6:payload_end], canonical,
    )


def status_action(status: int, *, receive_polls: int = 0, resends: int = 0) -> AuroraStatusAction:
    policy = LAMZU_AURORA_MODERN.status_timing
    assert policy is not None
    if status in policy.completed_statuses:
        return AuroraStatusAction.COMPLETE
    if policy.poll_below is not None and status < policy.poll_below:
        if receive_polls >= policy.maximum_receive_polls:
            raise AuroraKnowledgeError("bounded Aurora receive-poll limit reached")
        return AuroraStatusAction.POLL_RECEIVE
    if policy.resend_above is not None and status > policy.resend_above:
        if resends >= policy.maximum_resends:
            raise AuroraKnowledgeError("bounded Aurora resend limit reached")
        return AuroraStatusAction.RESEND
    raise AuroraKnowledgeError(f"unclassified Aurora status 0x{status:02x}")


def status_dialogue_kind(
    status: int,
    *,
    receive_polls: int = 0,
    resends: int = 0,
) -> DialogueKind:
    """Map vendor status evidence into the existing temporal vocabulary."""

    action = status_action(status, receive_polls=receive_polls, resends=resends)
    if action is AuroraStatusAction.COMPLETE:
        return DialogueKind.RESPONSE
    if action is AuroraStatusAction.POLL_RECEIVE:
        return DialogueKind.BUSY_PENDING
    return DialogueKind.RESPONSE_POLL


def decode_sensor_model(code: int, *, catalog_max_dpi: int | None = None) -> AuroraSensorModel:
    table = {
        1: AuroraSensorModel(1, "3395", (10, 20), 26000, 50, False),
        2: AuroraSensorModel(2, "3950", (7, 10, 20), 30000, 50, False),
        4: AuroraSensorModel(4, "3955", (7, 10, 13, 15, 17), max(40000, catalog_max_dpi or 0), 1, True),
    }
    try:
        return table[code]
    except KeyError as exc:
        raise AuroraKnowledgeError(f"unknown Aurora sensor code {code}") from exc


def encode_lod_tenths_mm(value: int) -> int:
    if value == 7:
        return 0x87
    if value in (10, 20):
        return value // 10
    if value in (13, 15, 17):
        return ((value // 10) << 4) | (value % 10)
    raise AuroraKnowledgeError("LOD value is outside the vendor-observed domain")


def decode_lod_tenths_mm(raw: int) -> int:
    if raw == 0x87:
        return 7
    if raw in (1, 2):
        return raw * 10
    high, low = raw >> 4, raw & 0x0F
    if high == 1 and low in (3, 5, 7):
        return 10 + low
    raise AuroraKnowledgeError("unknown Aurora LOD encoding")


def encode_angle_tune(value: int) -> int:
    if not -128 <= value <= 127:
        raise AuroraKnowledgeError("Angle Tune must fit signed 8-bit")
    return value & 0xFF


def decode_angle_tune(raw: int) -> int:
    if not 0 <= raw <= 0xFF:
        raise AuroraKnowledgeError("Angle Tune byte is invalid")
    return raw - 0x100 if raw & 0x80 else raw


def encode_rapid_trigger(profile: int, *, left: bool, right: bool) -> bytes:
    if not 1 <= profile <= 0xFF:
        raise AuroraKnowledgeError("profile must be a one-based byte")
    return bytes((profile, int(left), int(right)))


def encode_scroll_bhop(profile: int, *, mode: int, window_ms: int) -> bytes:
    if not 1 <= profile <= 0xFF or mode not in (0, 2, 3):
        raise AuroraKnowledgeError("invalid Scroll Bhop profile or mode")
    if window_ms not in (200, 400, 600, 800, 1000):
        raise AuroraKnowledgeError("invalid Scroll Bhop response window")
    return bytes((profile, mode)) + window_ms.to_bytes(2, "big")


def decode_battery_read(payload: bytes) -> AuroraBatteryState:
    if len(payload) < 2 or payload[0] not in (0, 1) or payload[1] > 100:
        raise AuroraKnowledgeError("invalid Aurora battery read")
    return AuroraBatteryState(payload[1], bool(payload[0]))


def decode_routed_identity(payload: bytes) -> AuroraRoutedIdentity:
    if len(payload) < 4:
        raise AuroraKnowledgeError("routed identity requires VID/PID BE16 values")
    return AuroraRoutedIdentity(
        int.from_bytes(payload[:2], "big"), int.from_bytes(payload[2:4], "big")
    )


def receiver_identity_ambiguity(usb_pid: int, routed_pid: int) -> str | None:
    if {usb_pid, routed_pid} == {0x0032, 0x002E}:
        return "USB receiver 0032 and routed/internal identity 002e remain distinct unresolved layers"
    return None


def decode_event(payload: bytes) -> AuroraEvent:
    if len(payload) < 2 or payload[0] != 0x04:
        raise AuroraKnowledgeError("not an Aurora Input Report 4 event")
    event = payload[1]
    if event == 0x01:
        if len(payload) < 7:
            raise AuroraKnowledgeError("DPI event is incomplete")
        values = {
            "active_stage": payload[2],
            "x_dpi": int.from_bytes(payload[3:5], "big"),
            "y_dpi": int.from_bytes(payload[5:7], "big"),
        }
        name = "dpi"
    elif event == 0x02:
        values, name = {"reread_required": True}, "profile"
    elif event == 0x03:
        if len(payload) < 4 or payload[2] > 100 or payload[3] not in (0, 1):
            raise AuroraKnowledgeError("battery event is invalid")
        values, name = {"percent": payload[2], "charging": bool(payload[3])}, "battery"
    elif event == 0x06:
        if len(payload) < 3 or payload[2] not in (0, 1):
            raise AuroraKnowledgeError("connection event is invalid")
        values, name = {"connected": bool(payload[2])}, "connection"
    elif event == 0x07:
        if len(payload) < 3:
            raise AuroraKnowledgeError("LOD event is incomplete")
        values, name = {"lod_tenths_mm": decode_lod_tenths_mm(payload[2])}, "lod"
    elif event == 0x08:
        if len(payload) < 3:
            raise AuroraKnowledgeError("polling event is incomplete")
        values, name = {"raw_polling": payload[2]}, "polling"
    elif event == 0x0D:
        if len(payload) < 4 or payload[2] not in (0, 1) or payload[3] not in (0, 1):
            raise AuroraKnowledgeError("performance event is invalid")
        selector, tracking = bool(payload[2]), bool(payload[3])
        if tracking and not selector:
            raise AuroraKnowledgeError("20K state violates its Competition prerequisite")
        mode = "20k" if tracking else "competition" if selector else "high_speed"
        values, name = {
            "competition": selector, "tracking_20k": tracking, "mode": mode,
        }, "performance"
    else:
        raise AuroraKnowledgeError(f"unknown Aurora event 0x{event:02x}")
    return AuroraEvent(event, name, values, bytes(payload))


def event_to_pushed_states(
    observation: DialogueObservation,
    *,
    freshness: StateFreshness = StateFreshness.FRESH,
) -> tuple[PushedStateRecord, ...]:
    """Project a decoded event into the existing pushed-state vocabulary."""

    if observation.report_id != 0x04:
        raise AuroraKnowledgeError("Aurora pushed state requires Input Report 4")
    event = decode_event(observation.payload)
    if event.name == "battery":
        states = (
            ("lamzu.battery_percent", int(event.values["percent"])),
            ("lamzu.battery_charging", int(bool(event.values["charging"]))),
        )
    else:
        states = tuple(
            (f"lamzu.{event.name}.{name}", int(value) if isinstance(value, bool) else value)
            for name, value in event.values.items()
        )
    return tuple(PushedStateRecord(
        observation=observation,
        semantic_state_id=name,
        decoded_state=value,
        freshness=freshness,
        freshness_reasons=("vendor-defined Input Report 4 event",),
        association=PushedStateAssociation.UNSOLICITED,
        accepted=True,
        subtype=event.event_id,
        transformed_payload=event.raw,
    ) for name, value in states)


def legacy_checksum(payload_without_checksum: bytes, *, report_id: int = 8) -> int:
    if len(payload_without_checksum) != 15 or not 0 <= report_id <= 0xFF:
        raise AuroraKnowledgeError("legacy checksum requires 15 packet bytes and one report ID")
    return (0x55 - report_id - sum(payload_without_checksum)) & 0xFF
