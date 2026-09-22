import { canConfirm, getCandidates, initialState, profiles, speedLabels, transition } from "./state.mjs";

let state = initialState();
let toastTimer;
let lastDialogTrigger;
const byId = (id) => document.getElementById(id);
const dialog = byId("detail-dialog");
const views = {
  overview: ["Overview", "A clear view of every decision.", "Your colony, its next move, and the reasoning behind it."],
  plans: ["Plans & tasks", "From survival to a lasting colony.", "Long-term intent, current goals, and bounded next steps."],
  matrices: ["Decision matrix", "A small set of inspectable choices.", "Review the policy before the selector makes its next move."],
  lessons: ["Lessons learned", "Remember the context. Keep the evidence.", "Persistent lessons with scope, counterexamples, and human review."],
  runtime: ["Game & agent", "Three parts, running together.", "Understand the game window, agent process, and browser interface."],
  settings: ["Settings", "Different endpoints. The same framework.", "Two independent model roles with versioned configuration."],
};

function notify(message) {
  clearTimeout(toastTimer);
  byId("toast").textContent = message;
  byId("toast").hidden = false;
  toastTimer = setTimeout(() => { byId("toast").hidden = true; }, 6500);
}

function dispatch(action) {
  state = transition(state, action);
  render();
}

function render() {
  const options = getCandidates(state.profile);
  const selected = options.find((candidate) => candidate.id === state.candidate);
  const profile = profiles[state.profile];
  byId("game-status").textContent = state.gameSpeed === 0 ? "Paused" : "Running";
  byId("game-dot").classList.toggle("paused", state.gameSpeed === 0);
  byId("pause-game").textContent = state.gameSpeed === 0 ? "Resume game" : "Pause game";
  byId("pause-game").setAttribute("aria-pressed", String(state.gameSpeed === 0));
  byId("speed-caption").textContent = speedLabels[state.gameSpeed];
  byId("agent-status").textContent = state.agentPaused ? "Paused" : state.mode === "manual" ? "Manual" : "Ready";
  byId("agent-dot").classList.toggle("paused", state.agentPaused || state.mode === "manual");
  byId("pause-agent").textContent = state.agentPaused ? "Resume agent" : "Pause agent";
  byId("pause-agent").setAttribute("aria-pressed", String(state.agentPaused));
  byId("mode").value = state.mode;
  byId("pawn-profile").value = state.profile;
  byId("map-overlay").checked = state.overlay;
  document.querySelectorAll("[data-speed]").forEach((button) => {
    const selectedSpeed = Number(button.dataset.speed) === state.gameSpeed;
    button.classList.toggle("selected", selectedSpeed);
    button.setAttribute("aria-pressed", String(selectedSpeed));
  });
  byId("candidate-grid").replaceChildren(...options.map((candidate) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `candidate${candidate.id === state.candidate ? " active" : ""}`;
    button.dataset.candidate = candidate.id;
    button.setAttribute("aria-pressed", String(candidate.id === state.candidate));
    button.innerHTML = `<span class="candidate-letter">${candidate.letter} / ${candidate.option}</span><i class="selection-dot" aria-hidden="true"></i><strong>${candidate.name}</strong><span>${candidate.time}</span><span class="recommended-mark">${!candidate.eligible ? "Excluded · inspect why" : candidate.recommended ? "Suggested in this scenario" : "Available for review"}</span>`;
    return button;
  }));
  options.forEach((candidate) => {
    byId(`overlay-${candidate.id}`).style.display = state.overlay && candidate.id === state.candidate ? "" : "none";
  });
  byId("map-roof-label").textContent = profile.roof;
  const upgrading = state.profile === "high";
  byId("temporary-shelter").style.display = upgrading ? "" : "none";
  byId("shelter-count").textContent = upgrading ? "6" : "3";
  byId("shelter-status").textContent = upgrading ? "Temporary" : "Attention";
  byId("shelter-bar").style.width = upgrading ? "100%" : "50%";
  byId("shelter-summary").textContent = upgrading ? "Temporary shelter ready · evaluate upgrade" : "3 additional sleeping places needed";
  byId("map-heading").textContent = upgrading ? "From temporary shelter to a lasting home" : "A home before nightfall";
  byId("focus-title").textContent = upgrading ? "Evaluate durable shelter" : "Secure sleeping space";
  byId("focus-description").textContent = upgrading ? "Temporary shelter is ready in this alternate scenario. Evaluate a staged upgrade while retaining existing sleeping space." : "Three pawns need usable shelter before nightfall. Keep food production staffed.";
  byId("attention-reason").textContent = upgrading ? "Spare capacity available" : "Deadline approaching";
  byId("candidate-label").textContent = state.confirmed ? "Demo proposal approved · no game writes" : selected.eligible ? "Selected for review" : "Excluded from dispatch";
  byId("candidate-label").className = `status-text ${selected.eligible ? "green" : "amber"}`;
  byId("candidate-title").textContent = selected.title;
  byId("candidate-reason").textContent = selected.recommended ? profile.reason : selected.reason;
  byId("candidate-time").textContent = selected.time;
  byId("candidate-mining").textContent = selected.mining;
  byId("candidate-gate").textContent = selected.gate;
  byId("pawn-skill").textContent = profile.skill;
  byId("pawn-availability").textContent = profile.availability;
  byId("candidate-lesson").textContent = selected.lesson;
  byId("plan-selection").textContent = `${selected.name} · ${state.confirmed ? "approved in demo; awaiting real validation" : "under review"}`;
  byId("confirm-plan").disabled = !canConfirm(state);
  byId("confirm-plan").textContent = state.confirmed ? "Demo plan approved" : !selected.eligible ? "Candidate excluded" : state.agentPaused ? "Agent paused" : state.mode === "shadow" ? "Shadow: no dispatch" : state.mode === "manual" ? "Manual: human controls game" : state.mode === "autonomous" ? "Queue demo plan →" : "Approve demo plan →";
}

function renderRoute() {
  const requested = window.location.hash.slice(1) || "overview";
  const key = Object.hasOwn(views, requested) ? requested : "overview";
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== `view-${key}`; });
  document.querySelectorAll(".nav-link").forEach((link) => {
    const active = link.getAttribute("href") === `#${key}`;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const [label, title, subtitle] = views[key];
  byId("breadcrumb-view").textContent = label;
  byId("page-title").textContent = title;
  byId("page-subtitle").textContent = subtitle;
  document.title = `${label} — Northstar · UI prototype`;
}

function showDialog(eyebrow, title, body) {
  lastDialogTrigger = document.activeElement;
  byId("dialog-eyebrow").textContent = eyebrow;
  byId("dialog-title").textContent = title;
  byId("dialog-body").innerHTML = body;
  dialog.showModal();
}

function showTrace() {
  const candidate = getCandidates(state.profile).find((item) => item.id === state.candidate);
  showDialog("D-018 · ILLUSTRATIVE TRACE", candidate.title, `
    <p>This is a constructed example, not a model response or gameplay record.</p>
    <div class="trace-step"><span>01</span><div><h3>Goal → task</h3><p>Secure sleeping space → select a shelter site. ${state.profile === "high" ? "The alternate scenario assumes temporary shelter is already ready." : "Three of six pawns need additional usable shelter."}</p></div></div>
    <div class="trace-step"><span>02</span><div><h3>Facts and estimates</h3><p>${profiles[state.profile].skill}; ${profiles[state.profile].availability}. All rates and completion ranges are illustrative.</p></div></div>
    <div class="trace-step"><span>03</span><div><h3>Candidate → bounded option</h3><p>${candidate.option} binds to candidate demo.${state.profile}.${candidate.id}. Coordinates and phases belong to the validated site plan.</p></div></div>
    <div class="trace-step"><span>04</span><div><h3>Dispatch gate</h3><p>${candidate.gate} ${state.confirmed ? "Approved in the mockup only." : "No approval recorded."}</p></div></div>
    <div class="trace-step"><span>05</span><div><h3>Outcome → lesson</h3><p>No commands issued. No observed outcome. Verification would inspect completed shelter, access, beds, and temperature. An unchosen candidate has no measured result.</p></div></div>
  `);
}

function showLesson(id) {
  const lessons = {
    low: ["L-001 · USER PRIOR", "Low mining capacity → consider open construction", "Apply only when a surface or reuse option is feasible. Counterexamples include impassable surface terrain or existing usable excavated rooms. Compare matched starting saves before promoting a general preference."],
    high: ["L-002 · USER PRIOR", "Available skilled miners → evaluate excavation", "Assess the entire project: roof support, access, infestations, finishing, hauling, and lost survival labor. Compare surface stone as well as wood. A mountain interior is not automatically safe or fireproof."],
    reserved: ["L-003 · SYNTHETIC HYPOTHESIS", "Reserved labor must not be counted twice", "The proposed regression fixture makes the most skilled miner the only cook. A forecast must preserve cooking hours. This fixture has not been executed and has no observed outcome."],
  };
  const [eyebrow, title, explanation] = lessons[id];
  showDialog(eyebrow, title, `<p>${explanation}</p><dl><dt>Evidence</dt><dd>0 real gameplay runs. No accepted policy change.</dd><dt>Required before promotion</dt><dd>Immutable trace references, matching context, supporting and contradicting evidence, regression fixtures, controlled comparisons, and human approval.</dd><dt>Retrieval</dt><dd>Only an approved frozen snapshot can influence scored planning. Synthetic examples remain outside live lesson retrieval.</dd></dl><div class="callout">Marking this card reviewed is a local demonstration. It does not support the lesson or activate a policy.</div><button class="button primary" id="mark-reviewed">Mark reviewed in demo</button>`);
  byId("mark-reviewed").addEventListener("click", (event) => {
    event.currentTarget.textContent = "Reviewed · evidence still required";
    event.currentTarget.disabled = true;
    notify("Review acknowledged in this dialog. No lesson promoted.");
  });
}

byId("candidate-grid").addEventListener("click", (event) => {
  const button = event.target.closest("[data-candidate]");
  if (!button) return;
  const id = button.dataset.candidate;
  dispatch({ type: "candidate", value: id });
  byId("candidate-grid").querySelector(`[data-candidate="${id}"]`).focus();
});
document.querySelectorAll("[data-speed]").forEach((button) => button.addEventListener("click", () => {
  dispatch({ type: "speed", value: Number(button.dataset.speed) });
  notify(`Demo speed: ${speedLabels[state.gameSpeed]}. No live TPS measurement.`);
}));
byId("pause-game").addEventListener("click", () => {
  dispatch({ type: "pauseGame" });
  notify("Game pause changed in the demo. Agent pause is independent.");
});
byId("pause-agent").addEventListener("click", () => {
  dispatch({ type: "pauseAgent" });
  notify("Agent pause changed in the demo. Game speed is unchanged.");
});
byId("mode").addEventListener("change", (event) => dispatch({ type: "mode", value: event.target.value }));
byId("pawn-profile").addEventListener("change", (event) => {
  dispatch({ type: "profile", value: event.target.value });
  notify("Switched to a different illustrative scenario. Previous demo approval cleared.");
});
byId("map-overlay").addEventListener("change", (event) => dispatch({ type: "overlay", value: event.target.checked }));
byId("takeover").addEventListener("click", () => {
  dispatch({ type: "takeover" });
  notify("Demo handoff: game paused, agent paused, manual mode selected. A real handoff also needs pending-write reconciliation.");
});
byId("confirm-plan").addEventListener("click", () => {
  if (!canConfirm(state)) return;
  dispatch({ type: "confirm" });
  notify(state.candidate === "hybrid" ? "Demo approval: temporary shelter only. Future excavation still needs a separate review." : "Demo plan approved. No game commands were sent.");
});
byId("view-trace").addEventListener("click", showTrace);
byId("close-dialog").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => { lastDialogTrigger?.focus(); });
document.querySelectorAll("[data-inspect]").forEach((button) => button.addEventListener("click", () => {
  dispatch({ type: "candidate", value: button.dataset.inspect });
  showTrace();
}));
document.querySelectorAll("[data-lesson]").forEach((button) => button.addEventListener("click", () => showLesson(button.dataset.lesson)));
byId("lesson-filter").addEventListener("change", (event) => {
  document.querySelectorAll("[data-lesson-status]").forEach((card) => {
    card.hidden = event.target.value !== "all" && card.dataset.lessonStatus !== event.target.value;
  });
});
byId("settings-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const fields = Object.fromEntries(new FormData(event.currentTarget));
  const proposal = { kind: "ui_mockup_proposal", schema_status: "illustrative_not_a_runtime_schema", activate: false, ...fields };
  const url = URL.createObjectURL(new Blob([JSON.stringify(proposal, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "northstar-demo-proposal.json";
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  notify("Downloaded a local demo proposal. No endpoint was contacted.");
});
byId("reset-demo").addEventListener("click", () => {
  dispatch({ type: "reset" });
  byId("settings-form").reset();
  byId("lesson-filter").value = "all";
  document.querySelectorAll("[data-lesson-status]").forEach((card) => { card.hidden = false; });
  if (dialog.open) dialog.close();
  window.location.hash = "overview";
  notify("Demo reset. No persistent policy was changed.");
});
window.addEventListener("hashchange", () => {
  renderRoute();
  byId("main").focus({ preventScroll: true });
  window.scrollTo({ top: 0 });
});
render();
renderRoute();
