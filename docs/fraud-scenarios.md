# Configurable fraud scenarios

`ScenarioConfig` controls seed, entity counts, traffic volume, attack volume, start time, and
`enabled_patterns`. All generated events include customer, card, merchant, amount, currency,
timestamp, country, IP, device, merchant category, and authentication method.

| Pattern | Injection behavior | Signals expected to react |
|---|---|---|
| Account takeover | New attacker device, card-not-present auth, elevated auth failures | device novelty, failed auth, model |
| Card testing | Repeated sub-€3 payments on shared device/IP | amount baseline, velocity, graph |
| Impossible travel | Payment jumps to Singapore or Brazil | geographic distance |
| Unusual merchant | Luxury purchase of €800–€4,000 equivalent | category/amount baseline |
| High velocity | Payments compressed into short clusters | 1-minute/hour counts, spend |
| New device | Unique device for each authorization | device novelty, degree |
| Transaction burst | Clustered authorizations across victims | velocity and graph structure |
| Compromised merchant | Multiple victims converge on one merchant and few devices | merchant/component signals |
| Coordinated ring | Victims share device, IP, and merchant | shared counts, component, graph risk |

Benign traffic intentionally contains secondary devices, foreign travel, shared NAT IPs,
amount spikes, and higher-risk merchant categories. This overlap prevents the reference
benchmark from being a trivial “attack flag equals label” exercise.

Example customization:

```python
ScenarioConfig(
    seed=31,
    normal_events=10_000,
    fraud_events_per_pattern=40,
    enabled_patterns=("card_testing", "coordinated_ring"),
)
```

