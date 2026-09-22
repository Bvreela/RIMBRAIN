export const speedLabels = {
  0: "Paused · simulation stopped",
  1: "Normal · target 1×",
  2: "Fast · target 3×",
  3: "Superfast · target 6×",
  4: "Dev ultrafast · target 15×",
};

export const profiles = {
  balanced: {
    skill: "Mining 14",
    availability: "4 unreserved hours today · food labor protected",
    recommendation: "hybrid",
    reason: "Tonight’s deadline favors quick surface shelter. Available mining skill makes a later stone upgrade worth evaluating separately.",
    roof: "GRANITE · ROOF UNSURVEYED",
  },
  low: {
    skill: "Mining 3",
    availability: "Low effective throughput · 4 unreserved hours",
    recommendation: "open",
    reason: "Available mining throughput cannot meet the shelter deadline. A surface footprint and building materials are available in this example.",
    roof: "GRANITE · ROOF UNSURVEYED",
  },
  high: {
    skill: "Mining 14",
    availability: "8 unreserved hours · temporary shelter ready",
    recommendation: "excavation",
    reason: "This alternate scenario assumes temporary shelter and a completed roof/access survey. Available skilled mining labor justifies staged excavation.",
    roof: "GRANITE · DEMO SURVEY PASSED",
  },
  reserved: {
    skill: "Mining 14",
    availability: "0 unreserved hours · sole cook reservation",
    recommendation: "open",
    reason: "Mara is the only cook in this scenario. Mining skill contributes no available mining capacity while food production needs her.",
    roof: "GRANITE · ROOF UNSURVEYED",
  },
};

const candidates = [
  { id: "reuse", letter: "A", name: "Reuse existing", title: "Repair and reuse", time: "Not sufficient", mining: "None", option: "REUSE_EXISTING", lesson: "Capacity and usability checks" },
  { id: "open", letter: "B", name: "Open construction", title: "Build on open ground", time: "6–8 game hours", mining: "None", option: "OPEN_CONSTRUCTION", lesson: "L-001 · Untested surface-shelter prior" },
  { id: "excavation", letter: "C", name: "Excavation", title: "Make room inside the mountain", time: "2–3 game days", mining: "High", option: "EXCAVATION", lesson: "L-002 · Untested durable-shelter prior" },
  { id: "hybrid", letter: "D", name: "Hybrid", title: "Shelter now, stone later", time: "6–8 game hours", mining: "Deferred", option: "HYBRID", lesson: "L-001 + L-002 · Untested priors" },
];

export function getCandidates(profileId) {
  const profile = profiles[profileId];
  if (!profile) throw new RangeError("Unknown pawn profile");
  return candidates.map((candidate) => {
    let eligible = true;
    let gate = "Demo checks pass for surface work. Verify the actual map, materials, builders, and labor reservations before dispatch.";
    let reason = "Open-ground construction avoids mining delays. Surface stone is another material option to compare when supply and labor permit.";
    if (candidate.id === "reuse") {
      eligible = false;
      gate = "Excluded: existing space fits only 3 of 6 pawns. No feasible expansion has been validated in this example.";
      reason = "The current room remains useful temporary shelter, but reuse alone does not satisfy the sleeping-space goal.";
    } else if (candidate.id === "excavation") {
      eligible = profileId === "high";
      reason = "Excavated stone may offer protected space and lower structural fire exposure, conditional on actual materials, access, roofs, and threats.";
      gate = eligible
        ? "Alternate demo scenario: temporary shelter, roof support, access, and labor checks pass. Inspect again before each excavation phase."
        : "Excluded for immediate shelter: roof/access checks are incomplete and excavation misses tonight’s deadline.";
      if (profileId === "reserved") gate += " The skilled miner is also reserved for cooking.";
    } else if (candidate.id === "hybrid") {
      reason = "Use the surface footprint for immediate shelter. Keep any mountain upgrade as a separate, later goal after shelter and maintenance are verified.";
      gate = "Approve temporary shelter only. Excavation remains unapproved until roof, access, infestation conditions, and spare labor are evaluated.";
    }
    return { ...candidate, eligible, gate, reason, recommended: profile.recommendation === candidate.id };
  });
}

export function initialState() {
  return {
    gameSpeed: 3,
    previousSpeed: 3,
    agentPaused: false,
    mode: "supervised",
    profile: "balanced",
    candidate: "hybrid",
    overlay: true,
    confirmed: false,
  };
}

export function canConfirm(state) {
  const candidate = getCandidates(state.profile).find((item) => item.id === state.candidate);
  return Boolean(candidate?.eligible && !state.agentPaused && !state.confirmed && ["supervised", "autonomous"].includes(state.mode));
}

export function transition(state, action) {
  switch (action.type) {
    case "speed":
      if (![1, 2, 3, 4].includes(action.value)) throw new RangeError("Speed must be an integer from 1 to 4");
      return { ...state, gameSpeed: action.value, previousSpeed: action.value };
    case "pauseGame":
      return { ...state, gameSpeed: state.gameSpeed === 0 ? state.previousSpeed : 0 };
    case "pauseAgent":
      return { ...state, agentPaused: !state.agentPaused };
    case "mode":
      if (!["supervised", "shadow", "autonomous", "manual"].includes(action.value)) throw new RangeError("Unknown mode");
      return { ...state, mode: action.value, confirmed: false };
    case "takeover":
      return { ...state, gameSpeed: 0, agentPaused: true, mode: "manual", confirmed: false };
    case "candidate":
      if (!candidates.some((item) => item.id === action.value)) throw new RangeError("Unknown candidate");
      return { ...state, candidate: action.value, confirmed: false };
    case "profile":
      if (!Object.hasOwn(profiles, action.value)) throw new RangeError("Unknown profile");
      return { ...state, profile: action.value, candidate: profiles[action.value].recommendation, confirmed: false };
    case "overlay":
      return { ...state, overlay: Boolean(action.value) };
    case "confirm":
      return canConfirm(state) ? { ...state, confirmed: true } : state;
    case "reset":
      return initialState();
    default:
      throw new RangeError("Unknown demo action");
  }
}
