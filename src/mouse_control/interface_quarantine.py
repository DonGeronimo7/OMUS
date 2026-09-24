# SPDX-License-Identifier: AGPL-3.0-or-later
"""Explainable, generation-bound admission for Discovery research interfaces."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class InterfaceRole(str, Enum):
    NORMAL_INPUT = "normal_input"
    CONFIGURATION = "configuration"
    RECEIVER = "receiver"
    FIRMWARE = "firmware"
    BOOTLOADER = "bootloader"
    UNKNOWN = "unknown"


class InterfaceAccess(str, Enum):
    PASSIVE = "passive"
    READ = "read"
    MUTATE = "mutate"


@dataclass(frozen=True)
class ResearchInterface:
    physical_identity: str
    number: int
    descriptor_sha256: str
    generation: int
    usage_page: int
    usage: int
    report_ids: tuple[int, ...]
    directions: frozenset[str]
    kernel_driver: str
    role: InterfaceRole
    endpoint_owner: str

    def __post_init__(self) -> None:
        if (not self.physical_identity or self.number < 0 or self.generation < 0
                or len(self.descriptor_sha256) != 64
                or any(item not in {"input", "output", "feature"} for item in self.directions)
                or any(not 0 <= item <= 255 for item in self.report_ids)):
            raise ValueError("invalid exact interface identity")


@dataclass(frozen=True)
class InterfaceAdmission:
    interface: ResearchInterface
    access: InterfaceAccess
    admitted: bool
    reasons: tuple[str, ...]
    requires_experiment_authority: bool = False

    @property
    def runtime_write_authorized(self) -> bool:
        return False


@dataclass(frozen=True)
class InterfacePolicy:
    physical_identity: str
    number: int
    descriptor_sha256: str
    role: InterfaceRole
    allow_read: bool = True
    allow_mutation: bool = False


def admit_interface(interface: ResearchInterface, requested: InterfaceAccess, *,
                    current_generation: int, policies: tuple[InterfacePolicy, ...] = ()) -> InterfaceAdmission:
    reasons: list[str] = []
    matches = tuple(item for item in policies if item.physical_identity == interface.physical_identity
                    and item.number == interface.number)
    exact = tuple(item for item in matches if item.descriptor_sha256 == interface.descriptor_sha256
                  and item.role is interface.role)
    if interface.generation != current_generation:
        reasons.append("stale interface generation")
    if matches and not exact:
        reasons.append("descriptor or role differs from admitted interface")
    if len(exact) > 1:
        reasons.append("ambiguous interface policy")
    policy = exact[0] if len(exact) == 1 else None
    if requested is InterfaceAccess.MUTATE:
        if interface.role in {InterfaceRole.FIRMWARE, InterfaceRole.BOOTLOADER}:
            reasons.append("firmware interface belongs to separate trust domain")
        if interface.role in {InterfaceRole.NORMAL_INPUT, InterfaceRole.UNKNOWN}:
            reasons.append("normal-input or unknown interfaces are observation-only")
        if policy is None or not policy.allow_mutation:
            reasons.append("interface has no explicit mutation admission")
        if not ({"output", "feature"} & interface.directions):
            reasons.append("interface exposes no mutable report direction")
    elif requested is InterfaceAccess.READ:
        if policy is None or not policy.allow_read:
            reasons.append("interface has no explicit read admission")
        if "feature" not in interface.directions and "input" not in interface.directions:
            reasons.append("interface exposes no readable direction")
    # Passive observation is the conservative default, including unknown/vendor interfaces.
    return InterfaceAdmission(interface, requested, not reasons, tuple(reasons),
                              requested is InterfaceAccess.MUTATE)
