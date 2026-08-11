# Online/offline feature contract

## Online features

Online inference computes only information available immediately before authorization:

| Family | Features | Point-in-time rule |
|---|---|---|
| Velocity | transaction counts in 1 minute, 1 hour, 1 day; spend in 1 hour | Current payment excluded |
| Baseline | historical mean amount; current/historical ratio | Prior payments only |
| Geography | haversine distance from historical mean coordinates | Prior coordinates only |
| Novelty | first device, first merchant | Membership checked before insertion |
| Authentication | failed authorizations in 1 hour | Prior attempts only |
| Current context | authentication failure, card-not-present, high-risk category | Present-event facts only |
| Inter-arrival | seconds since previous customer payment, historical count | Previous timestamp only |
| Graph | shared device/IP customers, component size, entity degree | Graph before current edges |
| Entity exposure | merchant customer count, prior device/IP observations | Prior graph events only |
| Feedback graph | merchant concentration, neighborhood confirmed-fraud rate | Confirmations older than delay |

The feature store rejects event-time regression per customer. Equal timestamps are ordered by
transaction ID during offline replay. The single-process API lock establishes an arrival
order online.

## Offline-only fields

`is_fraud`, `fraud_pattern`, realized loss, and benchmark partition are offline-only. The
public request schema rejects fraud labels. Labels are used to train/evaluate models and,
after a delay, simulate confirmed-fraud feedback. They are never model inputs.

## Training/serving consistency

`build_point_in_time_dataset` replays events through `OnlineFeatureStore` and `FraudGraph`,
the same implementations called by the API. Chronological splitting happens after feature
materialization; thresholds use validation labels, while the reported test partition is not
used for fitting models or thresholds.

## Remaining leakage risks

The simulator generates entity populations before replay, but no population-wide future
statistics are exposed as features. In a real warehouse, late-arriving corrections, mutable
merchant attributes, and chargeback effective dates would need explicit as-of joins and
backfill tests.
