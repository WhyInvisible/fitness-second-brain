# Paces & HR zones

> How "what pace / what heart rate should this run be" gets answered. This file is the **method**: how training paces and HR zones are derived from a benchmark, which workout uses which zone, and when to re-benchmark.
>
> **The athlete's actual numbers live in [profile.md](../profile.md) → Current fitness** (benchmarks, max / resting / threshold HR, current VDOT and the pace + HR table derived from it). They are recomputed after every benchmark using the method below, and the change is noted there and in the log.
>
> Workout type definitions are in [MOC-workout-types](MOC-workout-types.md).

## The derivation chain

1. **Benchmark** — a recent, honestly-raced effort: 5K time trial, 10K, half or full marathon. Shorter tests are cheaper to recover from; longer ones say more about marathon fitness.
2. **VDOT** — look the result up in Daniels' tables (or the Daniels-Gilbert equations / a VDOT calculator). See [vdot-system](../concepts/vdot-system.md) and [race-performance-sets-training-pace](../concepts/race-performance-sets-training-pace.md).
3. **Training paces** — read E / M / T / I / R paces off the same VDOT row. Sanity-check the gaps with the [six-second-rule](../concepts/six-second-rule.md).
4. **HR zones** — from a *measured* max HR (or a measured threshold HR), using the % bands below.
5. **Field check** — the first LT1 and LT2 sessions on the new numbers confirm or correct them (see "Reading a session as a benchmark").
6. **Write it down** — update profile.md → Current fitness with the new table, the date and the source.

Prescribe from **current** fitness, not goal fitness. Goal marathon pace (from [goals.md](../goals.md)) is what MP segments rehearse; it is not what easy, threshold or interval paces are set from.

## HR zones

### From max HR

| Zone | % max HR | Use |
|---|---|---|
| **Z1 Recovery** | 60–68% | Recovery jogs, walks |
| **Z2 Easy / Aerobic** | 68–78% | Easy runs, long-run base |
| **Z3 Steady / Marathon** | 79–85% | Marathon pace, "comfortable but working" |
| **Z4a Sub-threshold (LT1)** | 84–88% | The Norwegian-style workhorse session, up to 2×/week |
| **Z4b Threshold (LT2)** | 88–92% | True threshold, ~1×/week |
| **Z5 VO2max** | 93–100% | Intervals, long hill repeats |

The bands overlap on purpose: individual thresholds vary by several percent. A measured LT1 / LT2 heart rate (from a lab test or a clean field session) beats the percentage every time.

**Getting max HR.** Age formulas (220 − age and its variants) can be 10+ bpm off for an individual, so treat them as a placeholder only. Measure it: the closing kilometre of an all-out 5K, or the last of a set of hard hill repeats. If HR is still climbing at the finish, the reading is a **floor** — true max is likely a little higher — and the next maximal effort (a tune-up race) is a chance to re-check.

### From threshold HR (alternative)

If threshold HR (LTHR) is known instead — e.g. from a solo 30-minute time trial, using average HR over the final 20 minutes — anchor Z4b on it. Assuming LTHR sits at roughly 90% of max, the table above converts to approximately:

| Zone | ≈ % of LTHR |
|---|---|
| Z1 | < 75% |
| Z2 | 75–87% |
| Z3 | 88–94% |
| Z4a (LT1) | 93–98% |
| Z4b (LT2) | 98–102% |
| Z5 | > 103% |

### Which metric governs which zone

Per [hr-governs-easy-pace-governs-hard](../concepts/hr-governs-easy-pace-governs-hard.md): **HR caps the easy end** (Z1–Z2), **HR + pace** together for threshold work, **pace (+ RPE)** for VO2max and faster, where cardiac lag makes HR useless on short reps. RPE overrides both on a bad day.

## Training paces from VDOT

### Intensity of each Daniels pace

| Pace | ≈ % VO2max | ≈ % max HR | What it is |
|---|---|---|---|
| **E** (easy / long) | 59–74% | 65–78% | Conversational aerobic running |
| **M** (marathon) | 75–84% | 80–89% | Race-equivalent marathon pace for the current VDOT |
| **T** (threshold) | 83–88% | 88–92% | The pace you could race for roughly an hour |
| **I** (interval) | 95–100% | 98–100% | VO2max work, reps of 3–5 min |
| **R** (repetition) | 105%+ | n/a | Speed and economy, short reps with full recovery |

Approximate values from Daniels, *Daniels' Running Formula* (pace-intensity chapters). Pfitzinger adds two marathon-specific bands keyed off marathon pace (Pfitzinger, *Advanced Marathoning*, Ch. 1 / Table 8.1): **long runs 10–20% slower than MP**, **general-aerobic runs 15–25% slower than MP**.

**LT1 (sub-threshold)** has no Daniels row. It sits between M and T, usually nearer T. Set it by heart rate (stable in Z4a across the reps) rather than by formula; see [workout-sub-threshold-lt1](../concepts/workout-sub-threshold-lt1.md) and [lactate-controlled-not-pace-controlled](../concepts/lactate-controlled-not-pace-controlled.md).

### Reference rows (formula-derived)

Computed from the Daniels-Gilbert equations, so they land within a few seconds of the published tables. Use the tables or a VDOT calculator for the athlete's actual row.

| VDOT | 5K | Half | Marathon | E (/km) | M (/km) | T (/km) | I (/km) |
|---|---|---|---|---|---|---|---|
| 35 | 26:59 | 2:04:13 | 4:16:06 | 6:30–7:45 | 6:04 | 5:40 | 5:13 |
| 40 | 24:06 | 1:50:54 | 3:49:37 | 5:51–6:59 | 5:27 | 5:06 | 4:41 |
| 45 | 21:49 | 1:40:14 | 3:28:16 | 5:19–6:22 | 4:56 | 4:38 | 4:16 |
| 50 | 19:56 | 1:31:31 | 3:10:40 | 4:54–5:52 | 4:31 | 4:15 | 3:55 |
| 55 | 18:22 | 1:24:16 | 2:55:55 | 4:32–5:26 | 4:10 | 3:56 | 3:37 |

R pace ≈ I pace minus ~6 s per 400 m (≈ 15 s/km), per the six-second rule. Strides run at roughly R pace, relaxed.

**Equivalent performances are not predictions.** They assume distance-specific preparation. If the athlete's longest recent run is well short of the race distance, the half and marathon columns are theoretical until the long runs catch up.

## Which workout uses which zone

| Workout | Zone / pace | Governing metric |
|---|---|---|
| [Recovery jog](../concepts/workout-recovery-jog.md) | Z1, slower than E | HR |
| [Easy run](../concepts/workout-easy-run.md) | Z2, E pace | HR |
| [Long run](../concepts/workout-long-run.md) | Z2, E pace / 10–20% slower than MP | HR |
| [Marathon-pace run / MP segments](../concepts/workout-marathon-pace.md) | Z3, M pace (goal MP late in the build) | Pace, HR as a check |
| [Progression run](../concepts/workout-progression-run.md) | Z2 building to Z3 | HR then pace |
| [Sub-threshold (LT1)](../concepts/workout-sub-threshold-lt1.md) | Z4a, between M and T | HR stability |
| [Threshold (LT2)](../concepts/workout-threshold-lt2.md) | Z4b, T pace | Pace + HR |
| [VO2max intervals](../concepts/workout-vo2max-intervals.md) | Z5, I pace | Pace |
| [Long hill repeats](../concepts/workout-hill-repeats-long.md) | Z5 by effort | RPE |
| [Repetition](../concepts/workout-repetition.md) | R pace | Pace |
| [Strides](../concepts/workout-strides.md), [short hill sprints](../concepts/workout-short-hill-sprints.md) | ~R pace / near-max effort, short | RPE + form |
| [Fartlek](../concepts/workout-fartlek.md) | Mixed, T to I | RPE |

Volume limits per zone: [per-zone-weekly-volume-caps](../concepts/per-zone-weekly-volume-caps.md). Distribution: [80-20-rule](../concepts/80-20-rule.md).

## Reading a session as a benchmark

Race-derived VDOT gets the paces close; the first quality sessions on the new numbers tell you whether they are right.

- **LT1 — look at the HR drift across reps.** A true LT1 session holds HR roughly flat (a few bpm of rise across the reps). If HR climbs into the Z4b band by the last reps, the reps were above LT1: the prescription is slower than that pace, and the fix is to hold the HR, not to push through. Opening reps that are slow while HR is low are usually stiffness, not capacity; take the later reps as the rested figure.
- **LT2 — rep pace vs continuous pace.** Cruise intervals with Daniels' standard short recoveries (roughly 5:1 work:rest) typically run around 10–15 s/km faster than a continuous threshold effort. If recoveries were cut shorter than prescribed, the session sat closer to continuous and the gap shrinks (single digits). Use the rep figure to prescribe interval sessions and the continuous figure for race-pace maths. *(Rule of thumb, not a published constant.)*
- **Endurance-strong vs speed-weak.** A 5K-derived VDOT tends to under-rate a runner with strong aerobic endurance at the half and marathon. Low aerobic decoupling on long easy runs (HR drift vs pace under ~5%, the common rule of thumb) is the tell; if session-derived threshold pace beats the 5K-derived T pace, trust the sessions for longer-race maths.
- **Easy pace as a signpost, not a target.** Easy runs are run by HR and feel, never chased to a number. But easy pace drifting faster at the same HR over weeks is one of the most reliable signs fitness is improving, often more reliable than a single time trial. Watching which VDOT row's E range feels genuinely conversational is a cheap progress check between benchmarks.

## The gap check: current threshold vs goal marathon pace

The single most useful comparison in the table: **current T pace vs goal marathon pace** from [goals.md](../goals.md).

- Goal MP comfortably slower than current T → the target is consistent with current fitness; the build is about endurance and fuelling.
- Goal MP at or faster than current T → the goal currently asks for an hour-race effort held for three hours or more. The build has to close that gap; if the checkpoints show it isn't closing, retarget.

When projecting how fast VDOT will rise: gains during a comeback from a layoff come quickly because it is re-adaptation to a previous level; gains beyond the athlete's previous best come much more slowly. Don't extrapolate a comeback's rate of improvement into the peak block.

## When to re-benchmark

- At each checkpoint in the [season plan](../plans/season-plan.md) (typically a 5K time trial mid-base and a tune-up half 5–7 weeks out from a marathon).
- After any tune-up race, raced honestly.
- After a layoff, illness or injury break of more than ~2 weeks (until then, mark paces provisional and run by RPE).
- When easy-run HR at a given pace shifts consistently for 2+ weeks, or quality sessions feel consistently too easy or too hard on the current numbers.
- Max HR: whenever a maximal effort produces a higher reading than the one on file.

### Decision thresholds for checkpoints

Before each benchmark, write its result bands into the season plan so the call is made in advance, not rationalised afterwards. A typical shape:

| Result vs plan assumption | Reading | Action |
|---|---|---|
| Clearly faster | Ahead of plan | Keep building; consider whether the target is too conservative |
| Within the expected band | On track | No changes |
| Somewhat slower | Tight, no slack left | Next checkpoint becomes the decision point |
| Clearly slower | The plan's fitness assumption was wrong | **Retarget before the peak block, not after it** |

Translate each band into race times via the VDOT row it corresponds to.

**Don't run paces you can't yet sustain.** A threshold session run at goal-fitness threshold pace is really VO2max work with worse recovery. Train at what the athlete *currently* is, not what they want to be.

## RPE (rate of perceived exertion) cues

For runs without HR data or when the watch is unreliable:

| RPE | Feel | Speech test | Use |
|---|---|---|---|
| 1–2 | Very easy walk / shuffle | Could sing | — |
| 3 | Easy jog, fresh | Full conversation | Recovery jog |
| 4 | Easy, lightly working | Full sentences with some breath | Easy run base |
| 5 | Steady, comfortable | Short sentences | End of easy run, start of long run |
| 6 | Moderately hard, sustainable | Short phrases | Marathon pace |
| 7 | Comfortably hard, would last ~60 min | Few words at a time | Threshold |
| 8 | Hard, sustained discomfort | Single words | End of threshold, start of VO2max |
| 9 | Very hard, almost max | Grunts / nothing | VO2max intervals, hill repeats |
| 10 | All-out, can't sustain | None | Final race kick, max test |

## Recording a recalibration

Each time the numbers change, record in profile.md → Current fitness (and a line in the month's log):

```
YYYY-MM-DD — benchmark: <test, result, conditions>
             new VDOT: <x> (was <y>); max HR: <measured / estimated>
             what changed: <which paces / zones moved and by how much>
             why / caveats: <e.g. windy, under-raced, HR still rising at finish>
```

## Special-case considerations

- **Altitude** (roughly 1,500 m+): HR runs ~5–10 bpm higher at the same effort for the first 7–10 days. Slow paces accordingly; use RPE more than HR. Adaptation after ~2 weeks can bring easy HR back down, but don't bank on it if moving between altitudes.
- **Heat (>22°C)**: HR runs higher, paces slow ~10–15 s/km. Use RPE.
- **Wind and hills**: pace readings are unreliable; use HR and RPE, and don't treat a windy session as a clean benchmark.
- **Post-long-run easy runs**: legs are heavy, easy pace will feel slower than usual. Use HR (still in Z2), not pace.
- **Sick / poor sleep / high stress / alcohol the night before**: HR runs high. Cut intensity. If easy-run HR is climbing well above normal at normal pace, abandon and walk. A session run in this state is not a valid benchmark reading.

## Related

- [MOC-running](MOC-running.md) · [MOC-workout-types](MOC-workout-types.md) · [MOC-training-principles](MOC-training-principles.md)
- [vdot-system](../concepts/vdot-system.md) · [six-second-rule](../concepts/six-second-rule.md) · [race-performance-sets-training-pace](../concepts/race-performance-sets-training-pace.md)
- [hr-governs-easy-pace-governs-hard](../concepts/hr-governs-easy-pace-governs-hard.md) · [lactate-controlled-not-pace-controlled](../concepts/lactate-controlled-not-pace-controlled.md) · [per-zone-weekly-volume-caps](../concepts/per-zone-weekly-volume-caps.md)
