# Protocol Recognition Corpus

This document defines the first research-ingestion benchmark for the open-set
protocol recognizer. It is deliberately narrower than a claim about all mice.

## Recognition contract

The recognizer returns exactly one of:

- `UNKNOWN`: no repertoire family has sufficient structural evidence.
- `CANDIDATE`: one structural family remains but semantic evidence is absent or
  a required relationship failed.
- `AMBIGUOUS`: multiple families remain or a recognized family lacks the
  required score margin.
- `RECOGNIZED`: every required discriminator passed across enough independent
  evidence categories.

Every repertoire and open-set result is read-only. Recognition never grants a
runtime transaction, capability, or hardware write.

## First executable ingestion

| Family | Structural evidence | Executable semantic evidence | Current result |
|---|---|---|---|
| BITMOUSE `0x72` | paired 64-byte vendor Output/Input reports | request checksum; asymmetric marker placement; target, sequence, and declared-length relationships | `RECOGNIZED` when all relations pass |
| Keychron M6 | `FFC1`; `B3/B4` and `B5/B6` Output/Input namespaces | both query→response and setting→ACK report-ID pairings | `RECOGNIZED` when both dialogues are observed |
| Finalmouse ULX-style telemetry | vendor Output/Input reports; distinct mouse/dongle contexts | bounded response burst, exact namespace pairing, length+command+payload records | `RECOGNIZED` only for a completed valid burst |
| MCHOSE Realtek/L7 | vendor Input report `0x13`; Realtek pushed-state context | subtype `0x1D`, verified XOR-FF transform, periodic cadence or nudge-associated freshness | `RECOGNIZED` from passive or nudged pushed-state evidence |
| Holtek Venus `04d9:fc55` | interface 2; `FFA0`; Feature 2/16 and Feature 3/64 | not yet encoded because supplied research does not include safe passive frame samples | `CANDIDATE` only |

Holtek control/read/flash/status roles, commit/reset behavior, and polling
representation are recorded as descriptive facts. No executable write recipe
exists.

## Collision matrix

| Collision | Shared weak structure | Required discriminator | Expected outcome without it |
|---|---|---|---|
| BITMOUSE vs arbitrary `0x72` reports | report ID and 64-byte size | checksum plus target, sequence, and length correlation | `CANDIDATE` |
| Keychron vs generic 64-byte RPC | vendor page and report sizes | both paired namespaces (`B3→B4`, `B5→B6`) | `CANDIDATE` |
| Finalmouse vs unknown multi-response RPC | one Output followed by Input records | declared mouse/dongle namespace pair, bounded completion, cardinality, and record length | `CANDIDATE` |
| Holtek Venus vs Redragon/Holtek Feature protocols | `FFA0`, Feature IDs, reciprocal polling values | exact PID, interface, both exact lengths, then future semantic dialogue | `CANDIDATE` |
| SinoWealth plus Keychron descriptor collision | multiple independently valid structural signatures | family-specific semantic evidence and score margin | `AMBIGUOUS` |
| Unknown vendor protocol | vendor usage/report presence | no nearest-family fallback | `UNKNOWN` |

Values such as `08/04/02/01`, a vendor usage page, or a 64-byte report are never
sufficient family evidence alone.

## Project-owned benchmark fixtures

The automated corpus independently constructs eighteen minimal fixtures from
protocol facts; it imports no upstream capture:

1. identity-blinded valid BITMOUSE exchange;
2. BITMOUSE wrong-sequence near miss;
3. synthetic unknown grammar;
4. Keychron paired query/status and setting/ACK dialogues;
5. intentional SinoWealth/Keychron structural collision;
6. exact Holtek Venus structure without semantic traffic.
7. valid Finalmouse-style burst ending at the maximum record count;
8. valid Finalmouse-style quiet-interval completion;
9. valid Finalmouse-style deadline completion under continuous records;
10. wrong mouse/dongle namespace near miss;
11. unknown multi-response protocol.
12. valid periodic unsolicited MCHOSE-style state;
13. valid nudge followed by delayed asynchronous state;
14. stale immediate read superseded by a fresh delayed push;
15. wrong pushed-state subtype;
16. wrong XOR-FF transform;
17. old-generation pushed state;
18. unknown asynchronous protocol.

The expected current outcomes are eight recognized, eight candidates, one unknown,
and one ambiguous. This gives 100% recognized-family precision and known-case
recall, 0% unknown and collision false recognition, 44.4% overall coverage,
50% abstention, and 5.6% ambiguity **on this eighteen-case ingestion fixture only**.
It does not satisfy or claim the broader 90% objective; the positive set covers
only four executable families. The benchmark code reports these rates from the
actual decisions so later corpus expansion cannot silently redefine them.

## Asynchronous pushed-state model

Pushed state is meaningful without a request object. Each record retains exact
physical/source/transport/channel/namespace/report/grammar/generation identity,
a semantic state identity, decoded opaque state, freshness, freshness reasons,
periodic position, optional subtype/transform evidence, and an optional nudge
association. A nudge is an observed read-side eligibility fact, never an
executed command or runtime write permission.

Freshness is explicitly `FRESH`, `STALE`, or `UNKNOWN_FRESHNESS`. Evidence can
come from a bounded nudge association, periodic cadence, a monotonic state
counter, a state transition after a controlled physical action, or a later
accepted push that disagrees with an immediate read. A successful immediate
read starts with unknown freshness and becomes stale when superseded. Reports
from older connection generations are retained as rejected stale evidence and
cannot update current state.

The Realtek/L7 fixture intentionally claims no semantic field offsets. Report
ID `0x13`, subtype `0x1D`, and an actually verified XOR-FF source/result pair
are recognition evidence; transformed bytes remain opaque. Immediate Feature
buffers are not treated as authoritative merely because transport succeeded.

No asynchronous delivery shape currently identified in the research corpus
requires another temporal primitive: periodic pushes, nudged delayed pushes,
stale immediate reads, physical-action transitions, and receiver notices can
all be represented as one or more pushed-state stream specifications. Remaining
asynchronous-family work is recipe and corpus population. Fragmented logical
record reassembly, such as RAWM transport-vs-record boundaries, remains a
separate framing problem rather than an asynchronous-delivery limitation.

## Bounded response-burst model

The temporal assembler now represents one trigger followed by zero or more
correlated records. It terminates deterministically from replay timestamps on a
quiet interval, absolute deadline, maximum record count, explicit caller end,
or connection-generation change. Results retain the trigger, every accepted
record, timing, completion reason, confidence, generation, channel, and grammar.

Records must match the physical device, source, transport, response channel,
namespace, report ID, grammar, transaction tag when present, and connection
generation. Mouse movement, button/physical events, wrong namespaces/channels,
late records, and post-reconnect records cannot join the burst.

The current model intentionally requires one declared response channel,
namespace, report ID, and grammar per burst. It cannot yet describe one burst
whose valid records intentionally multiplex several response namespaces, nor
does it automatically decode an expected-count or terminator field from a
payload. A caller can end a burst explicitly, and expected-count protocols can
use the maximum-count bound only when that count is already known.

## Next corpus layers

Add independently reconstructed passive fixtures before promoting the remaining
research families. Priority evidence is GearHub internal device identity,
RAWM logical
record boundaries, VAXEE echo/direction/length, HyperX no-ACK readback, and Beken
prerequisite/apply state. Incomplete research remains negative or abstention
evidence rather than guessed semantics.
