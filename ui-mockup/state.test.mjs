import assert from "node:assert/strict";
import test from "node:test";
import { canConfirm, getCandidates, initialState, transition } from "./state.mjs";

test("game and agent pauses stay independent, including speed restoration", () => {
  let state = transition(initialState(), { type: "speed", value: 4 });
  state = transition(state, { type: "pauseAgent" });
  assert.equal(state.gameSpeed, 4);
  state = transition(state, { type: "pauseGame" });
  assert.equal(state.gameSpeed, 0);
  assert.equal(state.agentPaused, true);
  state = transition(state, { type: "pauseGame" });
  assert.equal(state.gameSpeed, 4);
  assert.equal(state.agentPaused, true);
});

test("human takeover remains non-dispatching even if game and agent are resumed", () => {
  let state = transition(initialState(), { type: "takeover" });
  assert.equal(state.gameSpeed, 0);
  assert.equal(state.agentPaused, true);
  assert.equal(state.mode, "manual");
  state = transition(state, { type: "speed", value: 3 });
  state = transition(state, { type: "pauseAgent" });
  assert.equal(canConfirm(state), false);
  assert.equal(transition(state, { type: "confirm" }).confirmed, false);
});

test("excluded candidates and shadow mode cannot be approved", () => {
  for (const candidate of ["reuse", "excavation"]) {
    const state = transition(initialState(), { type: "candidate", value: candidate });
    assert.equal(canConfirm(state), false);
    assert.equal(transition(state, { type: "confirm" }).confirmed, false);
  }
  const shadow = transition(initialState(), { type: "mode", value: "shadow" });
  assert.equal(canConfirm(shadow), false);
  assert.equal(transition(shadow, { type: "confirm" }).confirmed, false);
});

test("changed pawn availability invalidates approval and removes excavation eligibility", () => {
  let state = transition(initialState(), { type: "profile", value: "high" });
  assert.equal(state.candidate, "excavation");
  state = transition(state, { type: "confirm" });
  assert.equal(state.confirmed, true);
  state = transition(state, { type: "profile", value: "reserved" });
  assert.equal(state.confirmed, false);
  assert.equal(state.candidate, "open");
  assert.equal(getCandidates(state.profile).find((item) => item.id === "excavation").eligible, false);
});

test("candidate set stays bounded and rejects unsupported inputs", () => {
  for (const profile of ["balanced", "low", "high", "reserved"]) {
    const candidates = getCandidates(profile);
    assert.equal(candidates.length, 4);
    assert.equal(new Set(candidates.map((item) => item.option)).size, 4);
    assert.equal(candidates.filter((item) => item.recommended).length, 1);
    assert.equal(candidates.find((item) => item.recommended).eligible, true);
  }
  assert.throws(() => transition(initialState(), { type: "speed", value: 15 }), RangeError);
  assert.throws(() => transition(initialState(), { type: "candidate", value: "arbitrary_rpc" }), RangeError);
  assert.throws(() => transition(initialState(), { type: "profile", value: "unknown" }), RangeError);
});

test("one approval is idempotent and selecting another candidate invalidates it", () => {
  const state = transition(initialState(), { type: "confirm" });
  assert.equal(state.confirmed, true);
  assert.equal(canConfirm(state), false);
  assert.deepEqual(transition(state, { type: "confirm" }), state);
  assert.equal(transition(state, { type: "candidate", value: "open" }).confirmed, false);
  assert.deepEqual(transition(state, { type: "reset" }), initialState());
});
