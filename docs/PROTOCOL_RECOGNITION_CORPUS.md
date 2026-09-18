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
| Holtek Venus `04d9:fc55` | interface 2; `FFA0`; Feature 2/16 and Feature 3/64 | not yet encoded because supplied research does not include safe passive frame samples | `CANDIDATE` only |

Holtek control/read/flash/status roles, commit/reset behavior, and polling
representation are recorded as descriptive facts. No executable write recipe
exists.

## Collision matrix

| Collision | Shared weak structure | Required discriminator | Expected outcome without it |
|---|---|---|---|
| BITMOUSE vs arbitrary `0x72` reports | report ID and 64-byte size | checksum plus target, sequence, and length correlation | `CANDIDATE` |
| Keychron vs generic 64-byte RPC | vendor page and report sizes | both paired namespaces (`B3→B4`, `B5→B6`) | `CANDIDATE` |
| Holtek Venus vs Redragon/Holtek Feature protocols | `FFA0`, Feature IDs, reciprocal polling values | exact PID, interface, both exact lengths, then future semantic dialogue | `CANDIDATE` |
| SinoWealth plus Keychron descriptor collision | multiple independently valid structural signatures | family-specific semantic evidence and score margin | `AMBIGUOUS` |
| Unknown vendor protocol | vendor usage/report presence | no nearest-family fallback | `UNKNOWN` |

Values such as `08/04/02/01`, a vendor usage page, or a 64-byte report are never
sufficient family evidence alone.

## Project-owned benchmark fixtures

The automated corpus independently constructs six minimal fixtures from
protocol facts; it imports no upstream capture:

1. identity-blinded valid BITMOUSE exchange;
2. BITMOUSE wrong-sequence near miss;
3. synthetic unknown grammar;
4. Keychron paired query/status and setting/ACK dialogues;
5. intentional SinoWealth/Keychron structural collision;
6. exact Holtek Venus structure without semantic traffic.

The expected current outcomes are two recognized, two candidates, one unknown,
and one ambiguous. This gives 100% recognized-family precision and known-case
recall, 0% unknown and collision false recognition, 33.3% overall coverage,
50% abstention, and 16.7% ambiguity **on this six-case ingestion fixture only**.
It does not satisfy or claim the broader 90% objective; the positive set covers
only two executable families. The benchmark code reports these rates from the
actual decisions so later corpus expansion cannot silently redefine them.

## Next corpus layers

Add independently reconstructed passive fixtures before promoting the remaining
research families. Priority evidence is Finalmouse burst termination, GearHub
internal device identity, MCHOSE Realtek fresh asynchronous status, RAWM logical
record boundaries, VAXEE echo/direction/length, HyperX no-ACK readback, and Beken
prerequisite/apply state. Incomplete research remains negative or abstention
evidence rather than guessed semantics.
