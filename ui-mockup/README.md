# Northstar: RimWorld agent UI mockup

An interactive browser prototype of the proposed colony dashboard. **All colony
data, forecasts, map cells, decisions, and lesson records are illustrative.**
There is no RimWorld connection, model call, live telemetry, or active policy.
The game itself is not embedded. This is an executable UI artifact of the
[framework specification](../rimworld-jev-plan.html).

## Open the mockup

From the BVRimAgent repository root:

```sh
python3 -m http.server 8080 --bind 127.0.0.1
```

Then visit `http://127.0.0.1:8080/ui-mockup/` on that machine. Serving the parent
directory also makes the specification link work. ES modules require HTTP;
opening the HTML with a `file://` URL is not supported.

The browser has no runtime npm dependencies, external fonts, images, or analytics.
It uses HTML, CSS, JavaScript modules, and an original SVG schematic.

## Interactions

- Switch between overview, plans/tasks, decision matrix, lessons, runtime, and
  endpoint settings.
- Select any shelter candidate to inspect its map overlay and eligibility.
  Excluded candidates remain inspectable but cannot be approved.
- Change the pawn scenario to compare low mining capacity, a skilled available
  miner, or a skilled miner reserved as the only cook. Approval is invalidated
  when the scenario or selection changes.
- The alternate high-capacity scenario explicitly assumes temporary shelter and
  a completed survey. It does not claim that raw mining skill makes rock safe.
- Toggle the plan overlay and open decision traces.
- Pause the simulated game and agent independently. Take control pauses both and
  selects manual mode. Resuming either alone does not restore dispatch permission.
- Review lesson applicability and filter priors versus synthetic hypotheses.
  “Mark reviewed” only acknowledges the card in that dialog; it is not persisted
  and does not promote a lesson.
- Edit endpoint placeholders and download an inactive JSON demonstration proposal.
  It is not a runtime settings schema. No credentials should be entered.
- Reset all local demo state. Nothing persists after refresh.

## Checks

Use Node.js 22.13+ (validated here with Node 24) and npm for development checks:

```sh
npm ci
npm run lint
npm run check
npm test
```

ESLint is pinned as a development dependency. The six Node tests cover independent
pause state, takeover ownership, blocked/shadow dispatch, capacity changes,
bounded candidates, and approval invalidation. This is plain JavaScript, with
syntax checks and lint rather than a TypeScript build. These checks do not verify
browser rendering or gameplay.

## How the actual game and agent run together

```text
RimWorld process                    RimAgent Python process
  Game simulation                     Event and observation loop
  RimBridge mod        ← loopback →    Planner / selector adapters
  Optional Steward                    Action validation / outcome tracking
                                                ↕
                                      Browser dashboard
```

1. Run RimWorld with RimBridge and, optionally, Steward loaded. RimBridge exposes
   its local HTTP service on port 8765. Game operations are queued onto Unity's
   main thread; the HTTP request thread does not operate the simulation directly.
2. Run RimAgent separately. It reads state and events, calls model APIs, and sends
   actions to RimBridge. In-game Steward runs deterministic automation without a
   model call for each pawn action.
3. Use a browser for the dashboard, alongside the game window or on another
   monitor. Upstream RimAgent serves its existing dashboard on port 8770.
   This prototype runs separately on 8080 and is not wired into that server.
4. Enable RimWorld's “Run in background” option when using the browser while
   the game window is unfocused. This is ordinary background/windowed execution;
   no headless game setup has been verified.

The inspected upstream launcher uses macOS `open` commands. Its one-command launch
script is not a verified Linux or Windows setup procedure.

## Acceleration and operator control

RimBridge's `game.speed` accepts integer **settings** 0–4, with 0 meaning pause.
Speed number 3 does not mean 3×. The documented ordinary-map targets are:

| Setting | Mode | Target TPS | Typical multiplier | Ideal time per game day |
| --- | --- | ---: | ---: | ---: |
| 1 | Normal | 60 | 1× | 16m 40s |
| 2 | Fast | 180 | 3× | 5m 33s |
| 3 | Superfast | 360 | 6× | 2m 47s |
| 4 | Developer ultrafast | 900 | 15× | 1m 7s |

A game day is 60,000 ticks. These are target rates, not observed performance.
CPU load, maps, colony size, mods, threat slowdowns, loading, and decision pauses
reduce throughput. Some game states change the multiplier.

The normal UI exposes developer ultrafast after enabling Development mode in
RimWorld options and pressing `4`. The inspected RimBridge implementation directly
assigns `TimeSpeed` 4 without a `Prefs.DevMode` guard. Verify actual engine behavior
on the installed game/mod version rather than assuming that a successful RPC
means the target tick rate was achieved.

The inspected runner supports `play.speed`, `play.think_speed`, and
`play.danger_think_speed`. The repository YAML sets these to **3, 3, 1**;
Python fallback defaults use **3, 3, 0**. Resolve effective configuration rather
than assuming danger always pauses. A proposed initial policy is superfast during
calm work, pause or normal speed for danger/uncertainty, and measured ultrafast
evaluation once event-handling latency is understood.

Model API latency does not speed up with the game. Track actual TPS, game days
per wall-clock hour, event detection latency, observation age, and critical events
missed while thinking. Steward handles fast local reflexes; the model should not
be asked to decide every game tick.

**Pause ownership is unfinished integration work.** Upstream agent pause stops new
turns; it does not stop game simulation or cancel all work already in flight.
`with_pause` restores game speed after a thinking turn. A durable operator pause
therefore needs a shared pause/ownership contract, cancellation or reconciliation
of in-flight writes, and reconciliation of relevant Steward orders during a human
handoff. This mockup demonstrates the intended controls, not that integration.

Developer speed accelerates simulation. Instant construction, spawned resources,
instant research, or similar dev actions alter the experiment and should be kept
in separate assisted evaluation tracks. RimBridge's `dev.*` tools mark the ledger
as assisted; the inspected `game.speed` method does not itself set that flag.
Record speed policy and actual throughput with every evaluation run.

## Sources inspected

- [RimBridge speed and pause RPCs, inspected revision](https://github.com/zorrobyte/rimbridge/blob/3c1e4c7cee151104b85bf9c8372e113f91c5f08d/Source/Game/GameControl.cs)
- [RimBridge main-thread request queue](https://github.com/zorrobyte/rimbridge/blob/3c1e4c7cee151104b85bf9c8372e113f91c5f08d/Source/Server/MainThreadQueue.cs)
- [RimBridge assisted developer tools](https://github.com/zorrobyte/rimbridge/blob/3c1e4c7cee151104b85bf9c8372e113f91c5f08d/Source/Dev/DevRpc.cs)
- [RimAgent runner, inspected revision](https://github.com/zorrobyte/rimagent/blob/f4429eeb57ca87331a5ca619dbbc342575391417/agent/rimagent/runner.py)
- [RimAgent configuration](https://github.com/zorrobyte/rimagent/blob/f4429eeb57ca87331a5ca619dbbc342575391417/config.yaml)
- [RimAgent launcher](https://github.com/zorrobyte/rimagent/blob/f4429eeb57ca87331a5ca619dbbc342575391417/script/start.sh)
- [RimWorld Wiki: time](https://rimworldwiki.com/wiki/Time)
- [RimWorld Wiki: development mode](https://rimworldwiki.com/wiki/Development_mode)
- [Community confirmation of Run in background](https://steamcommunity.com/app/294100/discussions/0/1640927348812096160/)

This research is based on documentation and source inspection; no live RimWorld
instance was used to measure speed, test control ownership, or validate gameplay.
