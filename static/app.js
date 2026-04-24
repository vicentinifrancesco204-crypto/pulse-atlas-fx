const REFRESH_MS = 60_000;
const localeDateTime = new Intl.DateTimeFormat("it-IT", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

const MINDSET_PHRASES = [
  "Proteggi il capitale prima di inseguire il profitto.",
  "Un trade saltato pesa meno di un trade forzato.",
  "La pazienza paga piu della frenesia.",
  "Aspetta il livello, non inseguire la candela.",
  "Il mercato non ti deve nulla.",
  "Rispettare il risk management e gia performance.",
  "Una giornata piatta non richiede azione.",
  "La disciplina batte il talento senza regole.",
  "Se il setup non e chiaro, il no trade e posizione.",
  "Lascia parlare il prezzo prima del tuo ego.",
  "La tua edge vive nella ripetizione, non nell'improvvisazione.",
  "Ogni ingresso deve avere invalidazione chiara.",
  "Essere early non significa avere ragione.",
  "Il drawdown si riduce con selezione e calma.",
  "Chi controlla il rischio controlla la carriera.",
  "Pochi trade puliti valgono piu di dieci trade emotivi.",
  "Il mercato premia chi sa aspettare il timing.",
  "Taglia il caos, non allargare lo stop.",
  "La tua mente deve restare piu stabile del chart.",
  "Non difendere un'idea, leggi la struttura.",
  "Il prezzo puo restare irrazionale piu di quanto tu resti lucido.",
  "Ogni bias deve guadagnarsi conferma live.",
  "Un buon trade inizia con una buona rinuncia.",
  "La liquidita attira il mercato, non le speranze.",
  "Meglio perdere un'opportunita che perdere controllo.",
  "Il piano viene prima dell'impulso.",
  "Se non sai dove esci, non sai dove entri.",
  "Una lettura neutrale e meglio di una convinzione cieca.",
  "Lascia al mercato lo spazio di confermare.",
  "La size giusta tiene calma la testa.",
  "La coerenza costruisce piu del colpo di fortuna.",
  "Ogni giornata richiede adattamento, non orgoglio.",
  "I livelli contano piu delle opinioni.",
  "Un trade non cambia il mese, una cattiva abitudine si.",
  "Leggi il contesto prima del trigger.",
  "La sessione giusta vale mezzo setup.",
  "Il prezzo cerca inefficienze e liquidity, non narrative comode.",
  "Se sei emotivo, riduci la size o resta flat.",
  "L'assenza di edge oggi protegge l'edge di domani.",
  "Un breakout senza contesto e solo rumore costoso.",
  "La fretta trasforma la probabilita in errore.",
  "Un target chiaro evita uscite confuse.",
  "La conferma intraday vale piu dell'anticipazione.",
  "Essere selettivo e un vantaggio competitivo.",
  "Le migliori entrate sembrano quasi noiose.",
  "Non mediare il torto, rivaluta la struttura.",
  "Il mercato apre porte, ma non tutte vanno attraversate.",
  "Il vero edge e saper restare fuori quando serve.",
  "Una buona lettura inizia dai livelli gia presi.",
  "Osserva dove manca liquidity prima di pensare alla direzione.",
  "Ogni sessione va letta di nuovo, non copiata da ieri.",
  "La volatilita va rispettata, non sfidata.",
  "Non trasformare un'idea intraday in investimento emotivo.",
  "Il tuo obiettivo e eseguire bene, non indovinare tutto.",
  "Il mercato ama punire chi forza il timing.",
  "Rimani flessibile quando il flusso cambia.",
  "La qualita del trade conta piu della quantita.",
  "Prima la struttura, poi il trigger, poi la size.",
  "Non confondere movimento con opportunita.",
  "Se la lettura e sporca, la protezione deve essere pulita.",
];

const state = {
  currentPair: localStorage.getItem("pulse-atlas-pair") || "EURUSD",
  refreshTimer: null,
  dashboard: null,
  folders: {
    live: false,
    london: false,
    historical: false,
    future: false,
  },
};

const els = {
  pairSelect: document.getElementById("pair-select"),
  refreshButton: document.getElementById("refresh-button"),
  lastRefresh: document.getElementById("last-refresh"),
  feedState: document.getElementById("feed-state"),
  pairBadge: document.getElementById("pair-badge"),
  spotPrice: document.getElementById("spot-price"),
  spotChange: document.getElementById("spot-change"),
  spotNote: document.getElementById("spot-note"),
  mini1m: document.getElementById("mini-1m"),
  mini5m: document.getElementById("mini-5m"),
  generalChip: document.getElementById("general-chip"),
  generalTitle: document.getElementById("general-title"),
  generalSummary: document.getElementById("general-summary"),
  generalMeter: document.getElementById("general-meter"),
  generalDrivers: document.getElementById("general-drivers"),
  intradayChip: document.getElementById("intraday-chip"),
  intradayTitle: document.getElementById("intraday-title"),
  intradaySummary: document.getElementById("intraday-summary"),
  intradayMeter: document.getElementById("intraday-meter"),
  intradayDrivers: document.getElementById("intraday-drivers"),
  mindsetPhrase: document.getElementById("mindset-phrase"),
  mindsetSubtitle: document.getElementById("mindset-subtitle"),
  heroAnalysisTitle: document.getElementById("hero-analysis-title"),
  heroAnalysisSummary: document.getElementById("hero-analysis-summary"),
  heroAnalysisBody: document.getElementById("hero-analysis-body"),
  heroTargets: document.getElementById("hero-targets"),
  liveFolderToggle: document.getElementById("live-folder-toggle"),
  liveFolderSummary: document.getElementById("live-folder-summary"),
  liveFolderCount: document.getElementById("live-folder-count"),
  liveFolderContent: document.getElementById("live-folder-content"),
  intradayZones: document.getElementById("intraday-zones"),
  levelsGrid: document.getElementById("levels-grid"),
  londonFolderToggle: document.getElementById("london-folder-toggle"),
  londonFolderSummary: document.getElementById("london-folder-summary"),
  londonFolderCount: document.getElementById("london-folder-count"),
  londonFolderContent: document.getElementById("london-folder-content"),
  londonStats: document.getElementById("london-stats"),
  londonSummary: document.getElementById("london-summary"),
  londonAnalysis: document.getElementById("london-analysis"),
  londonZones: document.getElementById("london-zones"),
  historicalFolderToggle: document.getElementById("historical-folder-toggle"),
  historicalFolderSummary: document.getElementById("historical-folder-summary"),
  historicalFolderCount: document.getElementById("historical-folder-count"),
  historicalFolderContent: document.getElementById("historical-folder-content"),
  futureFolderToggle: document.getElementById("future-folder-toggle"),
  futureFolderSummary: document.getElementById("future-folder-summary"),
  futureFolderCount: document.getElementById("future-folder-count"),
  futureFolderContent: document.getElementById("future-folder-content"),
  macroList: document.getElementById("macro-list"),
  sessionList: document.getElementById("session-list"),
  spikeDialog: document.getElementById("spike-dialog"),
  dialogClose: document.getElementById("dialog-close"),
  dialogTitle: document.getElementById("dialog-title"),
  dialogSubtitle: document.getElementById("dialog-subtitle"),
  dialogSummary: document.getElementById("dialog-summary"),
  dialogMetrics: document.getElementById("dialog-metrics"),
  dialogReason: document.getElementById("dialog-reason"),
  dialogLiquidity: document.getElementById("dialog-liquidity"),
  dialogLevels: document.getElementById("dialog-levels"),
};

function setLoading() {
  els.feedState.textContent = "aggiornamento...";
  els.lastRefresh.textContent = "richiesta in corso";
}

function fmtPercent(value) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function toneClass(tone) {
  if (tone === "bullish") return "bullish";
  if (tone === "bearish") return "bearish";
  return "neutral";
}

function meterWidth(score) {
  return `${Math.max(8, Math.min(100, ((score + 7) / 14) * 100))}%`;
}

function toDate(value) {
  return new Date(value);
}

function formatPrice(value, pairCode) {
  const decimals = pairCode.endsWith("JPY") ? 3 : 5;
  return Number(value).toFixed(decimals);
}

function relativeCountdown(value) {
  const now = Date.now();
  const target = new Date(value).getTime();
  const diffMinutes = Math.round((target - now) / 60000);
  if (diffMinutes <= 0) return "in corso o gia passato";
  if (diffMinutes < 60) return `tra ${diffMinutes} min`;
  const hours = Math.floor(diffMinutes / 60);
  const minutes = diffMinutes % 60;
  if (hours < 24) return `tra ${hours}h ${minutes}m`;
  const days = Math.floor(hours / 24);
  return `tra ${days}g ${hours % 24}h`;
}

function renderMindset(meta, biasGeneral, biasIntraday) {
  const generatedAt = new Date(meta.generated_at);
  const minuteIndex = generatedAt.getHours() * 60 + generatedAt.getMinutes();
  const phraseIndex = minuteIndex % MINDSET_PHRASES.length;
  const biasLine = `Bias live: ${biasGeneral.label.toLowerCase()} sul quadro generale, ${biasIntraday.label.toLowerCase()} sull'intraday.`;
  els.mindsetPhrase.textContent = MINDSET_PHRASES[phraseIndex];
  els.mindsetSubtitle.textContent = biasLine;
}

function renderDrivers(target, items) {
  if (!items || !items.length) {
    target.innerHTML = "<li>Nessun driver disponibile in questo momento.</li>";
    return;
  }
  target.innerHTML = items.map((item) => `<li>${item}</li>`).join("");
}

function renderLevels(levels, pairCode) {
  const medianRange = levels.median_15m_range_pips ?? levels.median_5m_range_pips;
  const entries = [
    ["Session open", levels.session_open],
    ["Day high", levels.day_high],
    ["Day low", levels.day_low],
    ["Mid range", levels.day_mid],
    ["4h high", levels.four_hour_high],
    ["4h low", levels.four_hour_low],
    ["Median M15 range", `${medianRange.toFixed(1)} pips`],
    ["Last hour return", `${levels.recent_return_pips.toFixed(1)} pips`],
  ];

  els.levelsGrid.innerHTML = entries
    .map(([label, value]) => {
      const content = typeof value === "number" ? formatPrice(value, pairCode) : value;
      return `<div><span>${label}</span><strong>${content}</strong></div>`;
    })
    .join("");
}

function renderHeroAnalysis(intradayAi, pairCode) {
  els.heroAnalysisTitle.textContent = intradayAi.headline;
  els.heroAnalysisSummary.textContent = intradayAi.summary;
  els.heroAnalysisBody.textContent = intradayAi.analysis;
  els.heroTargets.innerHTML = intradayAi.targets
    .map((target) => `
      <div class="target-pill">
        <span>${target.label}</span>
        <strong>${formatPrice(target.price, pairCode)}</strong>
        <small>${target.distance_pips.toFixed(1)} pips</small>
      </div>
    `)
    .join("");
}

function renderIntradayZones(intradayAi, pairCode) {
  els.intradayZones.innerHTML = intradayAi.all_zones
    .map((zone) => `
      <article class="zone-card ${zone.status}">
        <div class="zone-top">
          <div>
            <p class="event-title">${zone.label}</p>
            <p class="event-sub">${zone.side} liquidity</p>
          </div>
          <span class="impact-badge ${zone.status}">${zone.status}</span>
        </div>
        <div class="metric-row">
          <span class="metric">Price: ${formatPrice(zone.price, pairCode)}</span>
          <span class="metric">Distance: ${Math.abs(zone.distance_pips).toFixed(1)} pips</span>
        </div>
        <p class="muted">${zone.why}</p>
      </article>
    `)
    .join("");
}

function renderLiveFolder(snapshot, intradayAi) {
  const zoneCount = intradayAi.all_zones.length;
  const targetText = intradayAi.targets.length
    ? intradayAi.targets.map((target) => target.label).join(", ")
    : "nessun target forte";
  els.liveFolderCount.textContent = `${zoneCount} zone`;
  els.liveFolderSummary.textContent =
    `${snapshot.price_label} con range ${snapshot.last_five_minute_range_pips.toFixed(1)} pips su 5m. Target piu vicini: ${targetText}.`;
  els.liveFolderContent.classList.toggle("hidden", !state.folders.live);
  els.liveFolderToggle.setAttribute("aria-expanded", String(state.folders.live));
}

function renderLondon(playbook, pairCode) {
  const stats = [
    ["London avg range", `${playbook.average_range_pips.toFixed(1)} pips`],
    ["London median range", `${playbook.median_range_pips.toFixed(1)} pips`],
    ["Sample size", `${playbook.sample_size} sessioni`],
    ["Next London window", localeDateTime.format(toDate(playbook.next_window))],
  ];

  els.londonStats.innerHTML = stats
    .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
    .join("");

  els.londonSummary.textContent = playbook.summary;
  els.londonAnalysis.textContent = playbook.ai_analysis;
  els.londonZones.innerHTML = playbook.zones
    .map((zone) => `
      <article class="zone-card ${zone.status_key}">
        <div class="zone-top">
          <div>
            <p class="event-title">${zone.label}</p>
            <p class="event-sub">${zone.side} liquidity</p>
          </div>
          <span class="impact-badge ${zone.status_key}">${zone.status}</span>
        </div>
        <div class="metric-row">
          <span class="metric">Price: ${formatPrice(zone.price, pairCode)}</span>
          <span class="metric">Distance: ${Math.abs(zone.distance_pips).toFixed(1)} pips</span>
        </div>
      </article>
    `)
    .join("");
}

function renderLondonFolder(playbook) {
  const nextWindow = localeDateTime.format(toDate(playbook.next_window));
  els.londonFolderCount.textContent = `${playbook.zones.length} zone`;
  els.londonFolderSummary.textContent =
    `London avg range ${playbook.average_range_pips.toFixed(1)} pips sugli ultimi ${playbook.sample_size} giorni. Prossima finestra: ${nextWindow}.`;
  els.londonFolderContent.classList.toggle("hidden", !state.folders.london);
  els.londonFolderToggle.setAttribute("aria-expanded", String(state.folders.london));
}

function renderHistorical(items) {
  els.historicalFolderCount.textContent = `${items.length} spike`;

  if (!items.length) {
    els.historicalFolderSummary.textContent = "Non ho trovato spike sopra soglia nell'ultimo campione live utile.";
    els.historicalFolderContent.innerHTML = `<div class="empty-state">Nessun historical spike significativo disponibile adesso.</div>`;
    els.historicalFolderContent.classList.toggle("hidden", !state.folders.historical);
    els.historicalFolderToggle.setAttribute("aria-expanded", String(state.folders.historical));
    return;
  }

  const latest = localeDateTime.format(toDate(items[0].time));
  els.historicalFolderSummary.textContent = `Archive live degli spike principali. Ultimo spike registrato: ${latest}.`;
  els.historicalFolderContent.innerHTML = items
    .map((item, index) => `
      <button class="folder-item" type="button" data-spike-index="${index}">
        <div>
          <p class="event-title">${item.reason_title}</p>
          <p class="event-sub">${localeDateTime.format(toDate(item.time))} - ${item.session} - impulso ${item.direction}</p>
        </div>
        <div class="folder-item-metrics">
          <span>${item.one_minute_pips.toFixed(1)} pips 1m</span>
          <span>${item.five_minute_pips.toFixed(1)} pips 5m</span>
        </div>
      </button>
    `)
    .join("");

  els.historicalFolderContent.classList.toggle("hidden", !state.folders.historical);
  els.historicalFolderToggle.setAttribute("aria-expanded", String(state.folders.historical));
}

function renderFuture(target, items, emptyMessage) {
  if (!items.length) {
    target.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
    return;
  }

  target.innerHTML = items
    .map((item) => {
      const when = localeDateTime.format(toDate(item.time));
      const probability = `${item.probability}%`;
      const impactClass = item.impact ? `impact-${item.impact.toLowerCase()}` : "impact-statistico";
      const extra = item.forecast || item.previous
        ? `<div class="metric-row">
            ${item.forecast ? `<span class="metric">Forecast: ${item.forecast}</span>` : ""}
            ${item.previous ? `<span class="metric">Previous: ${item.previous}</span>` : ""}
          </div>`
        : "";
      return `
        <article class="future-card">
          <div class="future-top">
            <div>
              <p class="future-title">${item.title}</p>
              <p class="future-sub">${when} - ${item.window_label} - ${relativeCountdown(item.time)}</p>
            </div>
            <div class="probability">${probability}</div>
          </div>
          <div class="metric-row">
            <span class="impact-badge ${impactClass}">${item.impact}</span>
            <span class="metric">Expected 1m: ${item.expected_one_minute_pips.toFixed(1)} pips</span>
            <span class="metric">Expected 5m: ${item.expected_five_minute_pips.toFixed(1)} pips</span>
          </div>
          <p class="muted">${item.reason}</p>
          ${extra}
        </article>
      `;
    })
    .join("");
}

function renderFutureFolder(futureCatalog) {
  const total = futureCatalog.macro.length + futureCatalog.sessions.length;
  const nextItem = [...futureCatalog.macro, ...futureCatalog.sessions]
    .sort((left, right) => new Date(left.time) - new Date(right.time))[0];
  els.futureFolderCount.textContent = `${total} window`;
  els.futureFolderSummary.textContent = nextItem
    ? `Prossima finestra sensibile: ${nextItem.title} ${relativeCountdown(nextItem.time)}.`
    : "Nessuna finestra futura forte disponibile nel blocco temporale corrente.";
  els.futureFolderContent.classList.toggle("hidden", !state.folders.future);
  els.futureFolderToggle.setAttribute("aria-expanded", String(state.folders.future));
}

function applyBias(cardId, chip, titleEl, summaryEl, meterEl, data) {
  const card = document.getElementById(cardId);
  chip.className = `tone-chip ${toneClass(data.tone)}`;
  chip.textContent = data.label;
  titleEl.textContent = data.label;
  summaryEl.textContent = `${data.summary} Confidenza ${data.confidence}%.`;
  meterEl.style.width = meterWidth(data.score);
  card.dataset.tone = data.tone;
}

function openSpikeDialog(index) {
  const item = state.dashboard?.historical_spikes?.[index];
  const pairCode = state.dashboard?.pair?.code;
  if (!item || !pairCode) {
    return;
  }

  els.dialogTitle.textContent = item.reason_title;
  els.dialogSubtitle.textContent = `${localeDateTime.format(toDate(item.time))} - ${item.session} - impulso ${item.direction}`;
  els.dialogSummary.textContent = item.detail_summary;
  els.dialogMetrics.innerHTML = `
    <span class="metric">1m jump: ${item.one_minute_pips.toFixed(1)} pips</span>
    <span class="metric">1m body: ${item.one_minute_body_pips.toFixed(1)} pips</span>
    <span class="metric">5m range: ${item.five_minute_pips.toFixed(1)} pips</span>
    <span class="metric">5m body: ${item.five_minute_body_pips.toFixed(1)} pips</span>
    ${item.impact ? `<span class="impact-badge impact-${item.impact.toLowerCase()}">${item.impact}</span>` : ""}
  `;
  els.dialogReason.textContent = item.event_title
    ? `${item.reason_body} Evento vicino: ${item.event_title}.`
    : item.reason_body;
  els.dialogLiquidity.innerHTML = item.liquidity_taken
    .map((entry) => `<div>${entry}</div>`)
    .join("");
  els.dialogLevels.innerHTML = Object.entries(item.reference_levels)
    .map(([label, value]) => `
      <div>
        <span>${label.replaceAll("_", " ")}</span>
        <strong>${formatPrice(value, pairCode)}</strong>
      </div>
    `)
    .join("");

  if (typeof els.spikeDialog.showModal === "function") {
    els.spikeDialog.showModal();
  }
}

function closeSpikeDialog() {
  if (els.spikeDialog.open) {
    els.spikeDialog.close();
  }
}

async function fetchPairs() {
  const response = await fetch("/api/pairs");
  if (!response.ok) {
    throw new Error("Impossibile caricare i pair");
  }
  const payload = await response.json();
  els.pairSelect.innerHTML = payload.pairs
    .map((pair) => `<option value="${pair.code}">${pair.label}</option>`)
    .join("");
  if ([...els.pairSelect.options].some((option) => option.value === state.currentPair)) {
    els.pairSelect.value = state.currentPair;
  } else {
    state.currentPair = payload.pairs[0]?.code || "EURUSD";
    els.pairSelect.value = state.currentPair;
  }
}

async function fetchDashboard() {
  setLoading();
  const response = await fetch(`/api/dashboard?symbol=${encodeURIComponent(state.currentPair)}`);
  if (!response.ok) {
    throw new Error("Impossibile caricare la dashboard live");
  }
  const payload = await response.json();
  state.dashboard = payload;
  renderDashboard(payload);
}

function renderDashboard(data) {
  const { pair, snapshot, meta, bias_general, bias_intraday, future_catalog, london_playbook, intraday_ai } = data;

  els.lastRefresh.textContent = localeDateTime.format(new Date(meta.generated_at));
  els.feedState.textContent = meta.live_state === "live"
    ? `live - ultimo tick ${meta.age_minutes} min fa`
    : `feed slow - ultimo tick ${meta.age_minutes} min fa`;

  els.pairBadge.textContent = pair.label;
  els.spotPrice.textContent = snapshot.price_label;
  els.spotChange.textContent = fmtPercent(snapshot.daily_change_pct);
  els.spotChange.className = `price-change ${snapshot.daily_change_pct < 0 ? "negative" : ""}`;
  els.spotNote.textContent = snapshot.market_note;
  els.mini1m.textContent = `${snapshot.last_minute_range_pips.toFixed(1)} pips`;
  els.mini5m.textContent = `${snapshot.last_five_minute_range_pips.toFixed(1)} pips`;

  renderMindset(meta, bias_general, bias_intraday);
  renderHeroAnalysis(intraday_ai, pair.code);
  renderIntradayZones(intraday_ai, pair.code);
  renderLiveFolder(snapshot, intraday_ai);

  applyBias("general-bias-card", els.generalChip, els.generalTitle, els.generalSummary, els.generalMeter, bias_general);
  applyBias("intraday-bias-card", els.intradayChip, els.intradayTitle, els.intradaySummary, els.intradayMeter, bias_intraday);

  renderDrivers(els.generalDrivers, bias_general.drivers);
  renderDrivers(els.intradayDrivers, bias_intraday.drivers);
  renderLevels(bias_intraday.levels, pair.code);
  renderLondon(london_playbook, pair.code);
  renderLondonFolder(london_playbook);
  renderHistorical(data.historical_spikes);
  renderFuture(els.macroList, future_catalog.macro, "Nessun macro event rilevante in arrivo nel calendario corrente del pair.");
  renderFuture(els.sessionList, future_catalog.sessions, "Nessuna recurring window forte disponibile nel prossimo blocco temporale.");
  renderFutureFolder(future_catalog);
}

function setErrorState() {
  els.feedState.textContent = "errore feed";
  els.lastRefresh.textContent = "richiesta fallita";
  els.liveFolderSummary.textContent = "Non sono riuscito a recuperare il quadro live. Riprova tra poco.";
  els.londonFolderSummary.textContent = "Il piano London non e disponibile in questo momento.";
  els.historicalFolderSummary.textContent = "Non sono riuscito a recuperare i dati live. Riprova tra poco.";
  els.futureFolderSummary.textContent = "Non sono riuscito a leggere le finestre future. Riprova tra poco.";
  els.historicalFolderContent.innerHTML = `<div class="empty-state">La richiesta live e fallita. Riprova tra poco.</div>`;
}

async function refresh() {
  try {
    await fetchDashboard();
  } catch (error) {
    console.error(error);
    setErrorState();
  }
}

function startAutoRefresh() {
  if (state.refreshTimer) {
    clearInterval(state.refreshTimer);
  }
  state.refreshTimer = setInterval(refresh, REFRESH_MS);
}

function toggleFolder(name, contentEl, toggleEl) {
  state.folders[name] = !state.folders[name];
  contentEl.classList.toggle("hidden", !state.folders[name]);
  toggleEl.setAttribute("aria-expanded", String(state.folders[name]));
}

function attachEvents() {
  els.pairSelect.addEventListener("change", async (event) => {
    state.currentPair = event.target.value;
    localStorage.setItem("pulse-atlas-pair", state.currentPair);
    closeSpikeDialog();
    await refresh();
  });

  els.refreshButton.addEventListener("click", refresh);

  els.liveFolderToggle.addEventListener("click", () => {
    toggleFolder("live", els.liveFolderContent, els.liveFolderToggle);
  });

  els.londonFolderToggle.addEventListener("click", () => {
    toggleFolder("london", els.londonFolderContent, els.londonFolderToggle);
  });

  els.historicalFolderToggle.addEventListener("click", () => {
    toggleFolder("historical", els.historicalFolderContent, els.historicalFolderToggle);
  });

  els.futureFolderToggle.addEventListener("click", () => {
    toggleFolder("future", els.futureFolderContent, els.futureFolderToggle);
  });

  els.historicalFolderContent.addEventListener("click", (event) => {
    const button = event.target.closest("[data-spike-index]");
    if (!button) {
      return;
    }
    openSpikeDialog(Number(button.dataset.spikeIndex));
  });

  els.dialogClose.addEventListener("click", closeSpikeDialog);
  els.spikeDialog.addEventListener("click", (event) => {
    if (event.target === els.spikeDialog) {
      closeSpikeDialog();
    }
  });
}

async function boot() {
  await fetchPairs();
  attachEvents();
  await refresh();
  startAutoRefresh();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}

boot().catch((error) => {
  console.error(error);
  els.feedState.textContent = "errore iniziale";
});
