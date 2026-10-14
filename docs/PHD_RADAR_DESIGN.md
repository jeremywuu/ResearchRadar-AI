# PhD Radar Design

## Purpose

The PhD radar supports a Fall 2028 application strategy without pretending that future cycles are
already open. It monitors durable academic entities and time-bounded application evidence while
keeping them semantically separate.

## Entity taxonomy

| Type | What it proves | What it does not prove |
|---|---|---|
| `PHD_PROGRAM_PROFILE` | An official programme exists and has stated research/training features | A current admission cycle or vacancy |
| `LAB_PROFILE` | An official laboratory exists and describes research topics/methods | That the lab is recruiting |
| `FACULTY_PROFILE` | A named faculty member and official research profile exist | Supervisor availability or willingness to recruit |
| `CONFIRMED_PHD_OPENING` | A first-party source explicitly announces an actionable opening | Future cycles beyond the stated opening |
| `APPLICATION_CYCLE_ANNOUNCEMENT` | A first-party source names an entry cycle and application state | Any later cycle |
| `FUNDING_OPPORTUNITY` | An official source states a distinct funding call | Admission or supervisor approval unless also stated |

These types are review semantics, not interchangeable opportunity statuses. Only actionable,
cycle-specific evidence may enter the existing `PhDOpportunity` pipeline. Programme, lab, and
faculty profiles remain `SourceCollectionResult.informational_profiles` and source metadata; they
do not create a parallel opportunity database or Google Sheets row.

## Required evidence

A profile may preserve:

- institution, programme, laboratory, and potential supervisor identities;
- official URLs and the retrieval timestamp;
- source-stated research topics and methods;
- application URL and general admissions information;
- source-stated funding information;
- admission cycle and recruitment state only when explicit.

Unknown facts remain `None`/`UNKNOWN`. A general “December 1” deadline can be retained as general
deadline information but is not copied into `official_deadline` without a named cycle. An existing
Fall 2027 announcement is historical/current-cycle evidence and never becomes Fall 2028 evidence.

## Fall 2028 lifecycle

1. Store verified programme/lab/faculty profiles as monitoring targets.
2. Reobserve first-party sources without manufacturing an opportunity.
3. When an official source names Fall 2028 entry, create an
   `APPLICATION_CYCLE_ANNOUNCEMENT` observation.
4. Create or update a `PhDOpportunity` only when the source states an actionable opening or
   programme application cycle.
5. Preserve earlier cycles under their own stable cycle-aware identity.
6. Never infer closure or non-recruitment from one missing page or HTTP failure.

## Identity and deduplication

Programme profiles use a stable source ID independent of admission cycles. Actionable PhD records
continue using the existing institution/programme-or-lab/cycle identity. The same UCL Gatsby 2027
programme evidence must retain its historical Record_ID; an alternate official URL is additional
provenance, not a new opportunity. A future 2028 cycle is a distinct cycle-aware record, not an
overwrite of 2027.

## Supervisor and lab monitoring

Potential supervisors should be ranked by research-topic and method evidence such as neural
representations, computational modeling, decision neuroscience, fMRI/EEG, RSA/MVPA, neural data,
and brain–ANN alignment. The UI/report label is `POTENTIAL_SUPERVISOR`, never “recruiting”, unless
an official source makes that claim. Contacting faculty remains outside ResearchRadar automation.

## Current source decisions

- CMU Neural Computation: verified programme profile; admission cycle unknown.
- Duke Cognitive Neuroscience: verified programme profile; cycle-specific deadline unknown.
- CMU Cognitive Neuroscience: verified informational profile; cycle unknown.
- Princeton Neuroscience: high-value Fall 2027 evidence but automated access blocked.
- UCL Gatsby and Gatsby-SWC: high-value 2027 evidence but automated access blocked.
- Yale Psychology: general admissions profile pending research-area/faculty evidence.

## Report presentation

The Weekly Brief should separate `Fall 2028 PhD Watch` from `Potential Supervisors & Labs` and
from `Application Open`. Each line should state the evidence type, official URL, observed cycle,
deadline confidence, funding confidence, and missing fields. Profiles must not appear in counts of
open PhD opportunities.
