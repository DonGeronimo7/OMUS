"""Deterministic observational profiles for decoded HID fields."""
from __future__ import annotations
from dataclasses import dataclass,field
from enum import Enum
from collections import Counter
from .hid_report import DecodedHidReport

class HidBehaviorClass(str,Enum):
    STATIC="static"; MOMENTARY="momentary"; PERSISTENT_STATE="persistent_state"; ENUM_STATE="enum_state"
    CYCLIC_STATE="cyclic_state"; COUNTER="counter"; CONTINUOUS="continuous"; MOTION_CORRELATED="motion_correlated"
    ACTION_CORRELATED="action_correlated"; UNKNOWN="unknown"

@dataclass
class HidFieldBehavior:
    field_id:str; observations:int=0; counts:Counter=field(default_factory=Counter); transitions:Counter=field(default_factory=Counter)
    minimum_seen:int|None=None; maximum_seen:int|None=None; changes:int=0
    _previous:int|None=None
    def observe(self,value:int)->None:
        self.observations+=1; self.counts[value]+=1
        self.minimum_seen=value if self.minimum_seen is None else min(self.minimum_seen,value)
        self.maximum_seen=value if self.maximum_seen is None else max(self.maximum_seen,value)
        if self._previous is not None and self._previous!=value: self.transitions[(self._previous,value)]+=1; self.changes+=1
        self._previous=value
    @property
    def unique_values(self): return tuple(sorted(self.counts))
    @property
    def change_rate(self): return self.changes/max(1,self.observations-1)
    @property
    def classification(self):
        values=self.unique_values
        if len(values)<=1: return HidBehaviorClass.STATIC
        ordered=list(self.transitions)
        # A one-way unit progression has counter evidence, even if its small
        # observed range could otherwise resemble an enum or a DPI cycle.
        if len(values)>=3 and ordered and all(b-a==1 for a,b in ordered): return HidBehaviorClass.COUNTER
        if len(values)<=8 and len(values)>=2:
            base=self.counts.most_common(1)[0][0]
            if len(values)>=3 and (max(values),min(values)) in self.transitions: return HidBehaviorClass.CYCLIC_STATE
            # A multi-value state that eventually returns to its baseline is
            # not a momentary button.  Restrict momentary recognition to the
            # binary press/release pattern so a complete stage cycle wins.
            if len(values)==2 and any(a==base and b!=base for a,b in self.transitions) and any(a!=base and b==base for a,b in self.transitions): return HidBehaviorClass.MOMENTARY
            return HidBehaviorClass.ENUM_STATE
        if ordered and all(b-a==1 for a,b in ordered): return HidBehaviorClass.COUNTER
        if self.change_rate>0.5: return HidBehaviorClass.CONTINUOUS
        return HidBehaviorClass.PERSISTENT_STATE
    def explanation(self): return f"{self.observations} observations, values={self.unique_values}, transitions={dict(self.transitions)}, change_rate={self.change_rate:.3f}"

def profile_reports(reports):
    result={}
    for report in reports:
        for value in report.values:
            if value.logical_value is not None: result.setdefault(value.field_id,HidFieldBehavior(value.field_id)).observe(value.logical_value)
    return result
