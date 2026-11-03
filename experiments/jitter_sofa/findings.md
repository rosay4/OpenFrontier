# Sofa bathroom comparison

Scene 5cdEh9F2hJL, original episode 0. The bathroom windows below were identified by visual inspection. Logs and simulator traces are under `output/jitter_compare_20261103_seed20261103/`. Both runs succeeded and neither logged a JITTER trigger or reset. The InternVL service sampled independently.

| Window (inclusive) | Frontier updates | Scoring steps | Logged replies | Invalid replies | Forward actions moving <5 cm |
| --- | ---: | ---: | ---: | ---: | ---: |
| Recovery 0, 50–76 | 4 | 3 | 3 | 0 | 7/11 |
| Recovery 1, 45–180 | 24 | 12 | 22 | 10 | 43/57 |

Scoring steps are distinct navigation steps with a logged frontier reply. Movement uses Habitat X/Z positions immediately before and after each action. Recovery 1 shows the same position at the sampled steps 90, 100, 110, 120 and 130. Its planner logged failed goals and deleted them near 94 and 173. Nine invalid replies occurred at step 175, after the prolonged stall was already underway.

The mirror appears in scoring text in both runs. Recovery 0 assigned A a 0.7 at step 55 and mentioned the mirror. Recovery 1 gave B a 0.0 at step 95 and mentioned reflective surfaces or bathroom fixtures at 121. This supports mirror exposure, but the logs do not associate the mirror pixels with a world-space frontier or establish that reflected geometry caused goal selection. Manager messages show both repeated merges into the same goal and changes of goal ID. The direct evidence is repeated ineffective forward movement plus recurring rescoring. An explanation to test is that reflected depth creates persistent invalid candidates that survive goal deletion or are redetected.
