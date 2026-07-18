/**
 * fritzbox-anrufe-card
 * ---------------------
 * Custom Lovelace card for the fritzbox_anrufe Home Assistant integration.
 *
 * Shows a filterable list of incoming/outgoing/missed FRITZ!Box calls plus
 * Anrufbeantworter (answering machine) messages, switched via a 5-icon
 * header bar (Alle / Eingehend / Ausgehend / Verpasst / Anrufbeantworter -
 * Anrufbeantworter is a tab like the others, not a separate section below
 * the call list), with a live-call banner above the icons whenever a call
 * is currently ringing/dialing/ongoing. Responsive: the layout stays
 * legible on both a phone-width and a desktop-width dashboard.
 *
 * Every category - Alle/Gesamt, Eingehend, Ausgehend, Verpasst and
 * Anrufbeantworter - can be individually shown or hidden via the graphical
 * config editor (or the matching show_* YAML key); the Anrufbeantworter tab
 * additionally only appears once entity_voicemail is configured. There is
 * deliberately only ONE card type: a dedicated, separate Anrufbeantworter
 * card was considered but dropped in favor of these per-category toggles on
 * this single card.
 *
 * Includes a graphical config editor (via getConfigElement) to pick the
 * entities, which categories are shown, the row count, and which call
 * attributes/columns are shown - no YAML editing required, though YAML
 * configuration still works.
 *
 * Playback: the FRITZ!Box audio recording is served by this integration's
 * own authenticated proxy endpoint (see http.py), which requires a valid
 * Home Assistant session - a plain <audio src="..."> cannot supply that
 * (browsers never attach Home Assistant's auth header to a bare media
 * src). The card therefore renders an "Abspielen" button per message that,
 * on click, downloads the audio via `hass.fetchWithAuth()` (the documented
 * custom-card API for authenticated fetches), turns the response into a
 * blob object URL, and only then hands it to a real <audio> element.
 *
 * Bundled with and auto-registered by the fritzbox_anrufe custom
 * integration (see custom_components/fritzbox_anrufe/__init__.py) - no
 * manual Lovelace resource registration needed.
 *
 * Example card configuration (YAML):
 *
 *   type: custom:fritzbox-anrufe-card
 *   title: FRITZ!Box Anrufe
 *   entity_live: sensor.fritz_box_7590_call_monitor
 *   entity_eingehend: sensor.fritz_box_7590_eingehende_anrufe
 *   entity_ausgehend: sensor.fritz_box_7590_ausgehende_anrufe
 *   entity_verpasst: sensor.fritz_box_7590_verpasste_anrufe
 *   entity_voicemail: sensor.fritz_box_7590_anrufbeantworter
 *   max_rows: 10
 *   show_alle: true
 *   show_eingehend: true
 *   show_ausgehend: true
 *   show_verpasst: true
 *   show_anrufbeantworter: true
 *   show_name: true
 *   show_number: true
 *   show_own_number: false
 *   show_device: true
 *   show_duration: true
 *   show_date: true
 *   show_vip: true
 */

const FILTER_ALL = "alle";
const FILTER_VOICEMAIL = "anrufbeantworter";
// "anrufbeantworter" is a tab like any other (5th icon in the header row),
// not a section rendered underneath the call list - see _renderMainContent().
const FILTER_ORDER = ["alle", "eingehend", "ausgehend", "verpasst", FILTER_VOICEMAIL];

const FILTER_META = {
  alle: { icon: "mdi:phone-log", label: "Alle" },
  eingehend: { icon: "mdi:phone-incoming", label: "Eingehend" },
  ausgehend: { icon: "mdi:phone-outgoing", label: "Ausgehend" },
  verpasst: { icon: "mdi:phone-missed", label: "Verpasst" },
  anrufbeantworter: { icon: "mdi:voicemail", label: "Anrufbeantworter" },
};

const LIVE_STATE_LABELS = {
  ringing: "Klingelt",
  dialing: "Wählen",
  talking: "Gespräch läuft",
};

const LIVE_INACTIVE_STATES = new Set(["idle", "unavailable", "unknown", ""]);

const CONFIG_DEFAULTS = {
  title: "FRITZ!Box Anrufe",
  max_rows: 10,
  // Kategorien/Tabs (Alle/Gesamt, Eingehend, Ausgehend, Verpasst,
  // Anrufbeantworter) einzeln ein-/ausblendbar. show_anrufbeantworter
  // wirkt zusätzlich zur Voraussetzung, dass entity_voicemail gesetzt ist -
  // siehe _visibleFilterTypes().
  show_alle: true,
  show_eingehend: true,
  show_ausgehend: true,
  show_verpasst: true,
  show_anrufbeantworter: true,
  // Spalten der Anrufliste einzeln ein-/ausblendbar.
  show_name: true,
  show_number: true,
  show_own_number: false,
  show_device: true,
  show_duration: true,
  show_date: true,
  show_vip: true,
};

function withDefaults(config) {
  return { ...CONFIG_DEFAULTS, ...(config || {}) };
}

function escapeHtml(value) {
  return String(value === undefined || value === null ? "" : value).replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c])
  );
}

function formatDateTime(iso) {
  if (!iso) return "";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// --- Anrufbeantworter row markup / styles -----------------------------------

function renderVoicemailRows(messages, opts) {
  const options = {
    showNumber: true,
    showDate: true,
    showDuration: true,
    maxRows: Infinity,
    ...(opts || {}),
  };
  const list = (messages || []).slice(0, options.maxRows);

  if (!list.length) {
    return `<div class="empty">Keine Nachrichten vorhanden.</div>`;
  }

  return `
    <div class="voicemail-rows">
      ${list
        .map(
          (msg) => `
        <div class="voicemail-row ${msg.new ? "unread" : ""}">
          <div class="voicemail-main">
            <div class="voicemail-primary">
              <span class="voicemail-name">${escapeHtml(msg.name || msg.number || "Unbekannt")}</span>
              ${msg.new ? '<span class="voicemail-badge">neu</span>' : ""}
            </div>
            <div class="voicemail-secondary">
              ${options.showNumber ? `<span>${escapeHtml(msg.number || "")}</span>` : ""}
              ${options.showDate ? `<span>${formatDateTime(msg.date)}</span>` : ""}
              ${options.showDuration && msg.duration ? `<span>${escapeHtml(msg.duration)}</span>` : ""}
            </div>
          </div>
          ${
            msg.media_url
              ? `<div class="voicemail-player-slot" data-media-url="${escapeHtml(msg.media_url)}">
                   <button class="voicemail-play-btn" type="button">
                     <ha-icon icon="mdi:play-circle-outline"></ha-icon>
                     <span>Abspielen</span>
                   </button>
                 </div>`
              : `<span class="voicemail-no-audio">Kein Wiedergabelink</span>`
          }
        </div>
      `
        )
        .join("")}
    </div>
  `;
}

const BASE_CARD_STYLES = `
  ha-card { overflow: hidden; }
  .card-content { padding: 8px 16px 16px; }
  .empty {
    padding: 24px 0;
    text-align: center;
    color: var(--secondary-text-color, #727272);
  }
`;

const VOICEMAIL_ROWS_STYLES = `
  .voicemail-rows { display: flex; flex-direction: column; gap: 10px; }
  .voicemail-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    border-radius: 8px;
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
  }
  .voicemail-row.unread { border-left: 3px solid var(--primary-color, #03a9f4); }
  .voicemail-main { display: flex; flex-direction: column; gap: 2px; }
  .voicemail-primary { display: flex; align-items: center; gap: 6px; }
  .voicemail-name { font-weight: 500; }
  .voicemail-badge {
    font-size: 0.7em;
    text-transform: uppercase;
    background: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
    border-radius: 4px;
    padding: 1px 6px;
  }
  .voicemail-secondary {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 0.8em;
    color: var(--secondary-text-color, #727272);
  }
  .voicemail-player-slot { margin-top: 2px; }
  .voicemail-player { width: 100%; height: 32px; }
  .voicemail-play-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    background: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
    font: inherit;
    font-size: 0.85em;
    cursor: pointer;
  }
  .voicemail-play-btn:disabled { opacity: 0.6; cursor: default; }
  .voicemail-play-btn ha-icon { --mdc-icon-size: 18px; }
  .voicemail-no-audio {
    font-size: 0.8em;
    color: var(--secondary-text-color, #727272);
    font-style: italic;
  }
`;

/**
 * Download one message's audio via the authenticated fetch API exposed to
 * custom cards (hass.fetchWithAuth), turn it into a blob object URL, and
 * swap the "Abspielen" button for a real, playable <audio> element.
 */
async function playVoicemail(hass, button, onObjectUrlCreated) {
  const slot = button.closest(".voicemail-player-slot");
  const mediaUrl = slot && slot.dataset.mediaUrl;
  if (!mediaUrl || !hass || !hass.fetchWithAuth) return;

  button.disabled = true;
  button.innerHTML = `<ha-icon icon="mdi:loading"></ha-icon><span>Lädt …</span>`;

  try {
    const response = await hass.fetchWithAuth(mediaUrl);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    if (onObjectUrlCreated) onObjectUrlCreated(objectUrl);

    const audio = document.createElement("audio");
    audio.controls = true;
    audio.autoplay = true;
    audio.className = "voicemail-player";
    audio.src = objectUrl;
    slot.replaceChildren(audio);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("fritzbox_anrufe: Anrufbeantworter-Wiedergabe fehlgeschlagen", err);
    button.disabled = false;
    button.innerHTML = `<ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>Fehler – erneut versuchen</span>`;
  }
}

// -----------------------------------------------------------------------
// fritzbox-anrufe-card
// -----------------------------------------------------------------------

class FritzboxAnrufeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._activeFilter = FILTER_ALL;
    this._hass = null;
    this._config = null;
    this._objectUrls = [];
    this._lastSignature = null;
  }

  setConfig(config) {
    if (!config) {
      throw new Error("fritzbox-anrufe-card: Konfiguration fehlt.");
    }
    if (!config.entity_eingehend || !config.entity_ausgehend || !config.entity_verpasst) {
      throw new Error(
        "fritzbox-anrufe-card: entity_eingehend, entity_ausgehend und entity_verpasst sind erforderlich."
      );
    }
    this._config = withDefaults(config);
    this._activeFilter = this._defaultFilter();
    this._lastSignature = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    // Lovelace pushes a new `hass` object on *every* state change anywhere
    // in Home Assistant, not just for this card's own entities. Rebuilding
    // the whole DOM on each of those would kill any Anrufbeantworter
    // playback in progress, so only actually re-render when something this
    // card cares about (its own entities, or the active tab) changed.
    const signature = this._computeSignature();
    if (signature === this._lastSignature && this.shadowRoot.firstChild) {
      return;
    }
    this._lastSignature = signature;
    this._render();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 5;
  }

  static getConfigElement() {
    return document.createElement("fritzbox-anrufe-card-editor");
  }

  static getStubConfig(hass, entities) {
    const guess = (suffix) =>
      (entities || []).find((e) => e.startsWith("sensor.") && e.includes(suffix)) || "";
    return {
      ...CONFIG_DEFAULTS,
      entity_live: guess("call_monitor") || guess("live"),
      entity_eingehend: guess("eingehend"),
      entity_ausgehend: guess("ausgehend"),
      entity_verpasst: guess("verpasst"),
      entity_voicemail: guess("anrufbeantworter") || guess("voicemail"),
    };
  }

  _entityState(entityId) {
    if (!entityId || !this._hass) return undefined;
    return this._hass.states[entityId];
  }

  // Kategorien (Tabs), die laut Konfiguration angezeigt werden sollen. Für
  // Anruf-Kategorien reicht der show_*-Schalter allein; die
  // Anrufbeantworter-Kategorie braucht zusätzlich einen konfigurierten
  // entity_voicemail - ohne Sensor gibt es dort nichts zu zeigen.
  _visibleFilterTypes() {
    return FILTER_ORDER.filter((type) => {
      if (this._config[`show_${type}`] === false) return false;
      if (type === FILTER_VOICEMAIL && !this._config.entity_voicemail) return false;
      return true;
    });
  }

  // Anruf-Typen (ohne "alle"), die in der "Alle"-Sammelansicht enthalten
  // sein sollen.
  _enabledCallTypes() {
    return ["eingehend", "ausgehend", "verpasst"].filter(
      (type) => this._config[`show_${type}`] !== false
    );
  }

  _defaultFilter() {
    const visible = this._visibleFilterTypes();
    if (visible.includes(FILTER_ALL)) return FILTER_ALL;
    return visible[0] || FILTER_ALL;
  }

  _computeSignature() {
    const ids = [
      this._config.entity_live,
      this._config.entity_eingehend,
      this._config.entity_ausgehend,
      this._config.entity_verpasst,
      this._config.entity_voicemail,
    ].filter(Boolean);
    const statePart = ids
      .map((id) => {
        const s = this._entityState(id);
        return s ? `${id}:${s.state}:${s.last_updated}` : `${id}:_`;
      })
      .join("|");
    return `${statePart}|filter:${this._activeFilter}`;
  }

  _callsFor(callType) {
    const key = `entity_${callType}`;
    const stateObj = this._entityState(this._config[key]);
    if (!stateObj) return [];
    const calls = stateObj.attributes ? stateObj.attributes.calls : undefined;
    return Array.isArray(calls) ? calls : [];
  }

  _visibleCalls() {
    const maxRows = Number(this._config.max_rows) || 10;
    if (this._activeFilter === FILTER_ALL) {
      const combined = this._enabledCallTypes().flatMap((type) => this._callsFor(type));
      combined.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
      return combined.slice(0, maxRows);
    }
    return this._callsFor(this._activeFilter).slice(0, maxRows);
  }

  _voicemails() {
    const stateObj = this._entityState(this._config.entity_voicemail);
    if (!stateObj) return [];
    const messages = stateObj.attributes ? stateObj.attributes.messages : undefined;
    return Array.isArray(messages) ? messages : [];
  }

  _liveStateObj() {
    return this._entityState(this._config.entity_live);
  }

  _isLiveActive() {
    const stateObj = this._liveStateObj();
    return !!stateObj && !LIVE_INACTIVE_STATES.has(stateObj.state);
  }

  _typeIcon(type) {
    return (FILTER_META[type] && FILTER_META[type].icon) || "mdi:phone";
  }

  _renderLiveBanner() {
    if (!this._isLiveActive()) return "";
    const stateObj = this._liveStateObj();
    const attrs = stateObj.attributes || {};
    const label = LIVE_STATE_LABELS[stateObj.state] || stateObj.state;
    const name = attrs.from_name || attrs.to_name || attrs.with_name || "";
    const number = attrs.from || attrs.to || attrs.with || "";
    const separator = name && number ? " · " : "";
    return `
      <div class="live-banner">
        <ha-icon icon="mdi:phone-in-talk"></ha-icon>
        <div class="live-banner-text">
          <span class="live-state">${escapeHtml(label)}</span>
          <span class="live-detail">${escapeHtml(name)}${separator}${escapeHtml(number)}</span>
        </div>
      </div>
    `;
  }

  _renderTabs() {
    const visible = this._visibleFilterTypes();
    if (visible.length <= 1) return "";
    return `
      <div class="tabs" role="tablist">
        ${visible
          .map((type) => {
            const meta = FILTER_META[type];
            const active = type === this._activeFilter ? "active" : "";
            return `
              <button
                class="tab ${active}"
                role="tab"
                aria-selected="${type === this._activeFilter}"
                data-filter="${type}"
                title="${escapeHtml(meta.label)}"
              >
                <ha-icon icon="${meta.icon}"></ha-icon>
                <span>${escapeHtml(meta.label)}</span>
              </button>
            `;
          })
          .join("")}
      </div>
    `;
  }

  // Anrufbeantworter ist ein Tab wie jeder andere (5. Symbol in der
  // Kopfzeile, siehe FILTER_ORDER) - kein Abschnitt unterhalb der
  // Anrufliste. Je nach aktivem Tab zeigt der Kartenkörper entweder die
  // Anrufliste oder die Anrufbeantworter-Nachrichten, nie beides.
  _renderMainContent() {
    if (this._activeFilter === FILTER_VOICEMAIL) {
      return this._renderVoicemailRows();
    }
    return this._renderRows();
  }

  _renderRows() {
    const calls = this._visibleCalls();
    const cfg = this._config;
    if (!calls.length) {
      return `<div class="empty">Keine Anrufe vorhanden.</div>`;
    }
    return `
      <div class="rows">
        ${calls
          .map(
            (call) => `
          <div class="row">
            <ha-icon class="row-icon" icon="${this._typeIcon(call.type)}"></ha-icon>
            <div class="row-main">
              <div class="row-primary">
                ${cfg.show_name ? `<span class="row-name">${escapeHtml(call.name || call.number || "Unbekannt")}</span>` : ""}
                ${cfg.show_vip && call.vip ? '<ha-icon class="vip" icon="mdi:star"></ha-icon>' : ""}
              </div>
              <div class="row-secondary">
                ${cfg.show_number ? `<span class="row-number">${escapeHtml(call.number || "")}</span>` : ""}
                ${cfg.show_own_number && call.own_number ? `<span class="row-own-number">${escapeHtml(call.own_number)}</span>` : ""}
                ${cfg.show_date ? `<span class="row-date">${formatDateTime(call.date)}</span>` : ""}
              </div>
            </div>
            <div class="row-extra">
              ${cfg.show_duration && call.duration ? `<span class="row-duration">${escapeHtml(call.duration)}</span>` : ""}
              ${cfg.show_device && call.device ? `<span class="row-device">${escapeHtml(call.device)}</span>` : ""}
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    `;
  }

  _renderVoicemailRows() {
    const maxRows = Number(this._config.max_rows) || 10;
    return renderVoicemailRows(this._voicemails(), { maxRows });
  }

  _revokeObjectUrls() {
    (this._objectUrls || []).forEach((u) => URL.revokeObjectURL(u));
    this._objectUrls = [];
  }

  _render() {
    if (!this._config || !this._hass) return;

    // A full re-render tears down and rebuilds every node below, including
    // any <audio> currently playing a downloaded recording - release the
    // blob URLs backing those before they become unreachable.
    this._revokeObjectUrls();

    // The active tab might no longer be visible (e.g. its category was just
    // switched off in the editor) - fall back before painting.
    if (!this._visibleFilterTypes().includes(this._activeFilter)) {
      this._activeFilter = this._defaultFilter();
    }

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card header="${escapeHtml(this._config.title)}">
        <div class="card-content">
          ${this._renderLiveBanner()}
          ${this._renderTabs()}
          ${this._renderMainContent()}
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._activeFilter = btn.dataset.filter;
        this._lastSignature = this._computeSignature();
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll(".voicemail-play-btn").forEach((btn) => {
      btn.addEventListener("click", () =>
        playVoicemail(this._hass, btn, (url) => this._objectUrls.push(url))
      );
    });
  }

  _styles() {
    return `
      ${BASE_CARD_STYLES}

      .live-banner {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        margin-bottom: 12px;
        border-radius: 8px;
        background: var(--state-icon-active-color, #03a9f4);
        color: var(--text-primary-color, #fff);
      }
      .live-banner ha-icon { --mdc-icon-size: 28px; flex-shrink: 0; }
      .live-banner-text { display: flex; flex-direction: column; min-width: 0; }
      .live-state { font-weight: 600; }
      .live-detail {
        font-size: 0.9em;
        opacity: 0.9;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .tabs {
        display: flex;
        gap: 4px;
        margin-bottom: 8px;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
        overflow-x: auto;
      }
      .tab {
        display: flex;
        align-items: center;
        gap: 6px;
        flex: 1 1 auto;
        justify-content: center;
        background: none;
        border: none;
        border-bottom: 2px solid transparent;
        padding: 8px 6px;
        cursor: pointer;
        color: var(--secondary-text-color, #727272);
        font: inherit;
        white-space: nowrap;
      }
      .tab ha-icon { --mdc-icon-size: 20px; }
      .tab.active {
        color: var(--primary-color, #03a9f4);
        border-bottom-color: var(--primary-color, #03a9f4);
        font-weight: 600;
      }
      .tab span { font-size: 0.8em; }

      .rows { display: flex; flex-direction: column; }
      .row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 0;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }
      .row:last-child { border-bottom: none; }
      .row-icon {
        flex-shrink: 0;
        color: var(--secondary-text-color, #727272);
        --mdc-icon-size: 20px;
      }
      .row-main { flex: 1 1 auto; min-width: 0; }
      .row-primary { display: flex; align-items: center; gap: 4px; }
      .row-name {
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .vip { --mdc-icon-size: 14px; color: var(--warning-color, #ff9800); }
      .row-secondary {
        display: flex;
        gap: 8px;
        font-size: 0.85em;
        color: var(--secondary-text-color, #727272);
        overflow: hidden;
      }
      .row-number,
      .row-own-number { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .row-date { flex-shrink: 0; }
      .row-extra {
        flex-shrink: 0;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 2px;
        font-size: 0.8em;
        color: var(--secondary-text-color, #727272);
        text-align: right;
      }

      ${VOICEMAIL_ROWS_STYLES}

      /* --- Responsive: schmale Ansicht (Smartphone) --- */
      @media (max-width: 500px) {
        .card-content { padding: 4px 10px 10px; }
        .tab span { display: none; }
        .tab ha-icon { --mdc-icon-size: 24px; }
        .row-extra .row-device { display: none; }
      }
    `;
  }
}

/**
 * fritzbox-anrufe-card-editor
 * -----------------------------
 * Graphical config editor shown by the Lovelace card picker/edit dialog.
 * Built on Home Assistant's own <ha-form> so it automatically matches the
 * standard HA look (entity pickers, toggles, number field) instead of a
 * hand-rolled UI.
 */

const EDITOR_LABELS = {
  title: "Titel",
  entity_live: "Sensor: Live-Anrufmonitor (optional)",
  entity_eingehend: "Sensor: Eingehende Anrufe",
  entity_ausgehend: "Sensor: Ausgehende Anrufe",
  entity_verpasst: "Sensor: Verpasste Anrufe",
  entity_voicemail: "Sensor: Anrufbeantworter (optional)",
  max_rows: "Max. Zeilen",
  show_alle: "Kategorie 'Gesamt' (Alle) anzeigen",
  show_eingehend: "Kategorie 'Eingehend' anzeigen",
  show_ausgehend: "Kategorie 'Ausgehend' anzeigen",
  show_verpasst: "Kategorie 'Verpasst' anzeigen",
  show_anrufbeantworter: "Kategorie 'Anrufbeantworter' anzeigen",
  show_name: "Name anzeigen",
  show_number: "Nummer anzeigen",
  show_own_number: "Eigene Rufnummer anzeigen",
  show_device: "Gerät anzeigen",
  show_duration: "Dauer anzeigen",
  show_date: "Datum/Uhrzeit anzeigen",
  show_vip: "VIP-Markierung anzeigen",
};

function computeEditorLabel(schemaItem) {
  return EDITOR_LABELS[schemaItem.name] || schemaItem.name;
}

const EDITOR_SCHEMA = [
  { name: "title", selector: { text: {} } },
  { name: "entity_live", selector: { entity: { domain: "sensor" } } },
  { name: "entity_eingehend", selector: { entity: { domain: "sensor" } } },
  { name: "entity_ausgehend", selector: { entity: { domain: "sensor" } } },
  { name: "entity_verpasst", selector: { entity: { domain: "sensor" } } },
  { name: "entity_voicemail", selector: { entity: { domain: "sensor" } } },
  { name: "max_rows", selector: { number: { min: 1, max: 200, mode: "box" } } },
  { name: "show_alle", selector: { boolean: {} } },
  { name: "show_eingehend", selector: { boolean: {} } },
  { name: "show_ausgehend", selector: { boolean: {} } },
  { name: "show_verpasst", selector: { boolean: {} } },
  { name: "show_anrufbeantworter", selector: { boolean: {} } },
  { name: "show_name", selector: { boolean: {} } },
  { name: "show_number", selector: { boolean: {} } },
  { name: "show_own_number", selector: { boolean: {} } },
  { name: "show_device", selector: { boolean: {} } },
  { name: "show_duration", selector: { boolean: {} } },
  { name: "show_date", selector: { boolean: {} } },
  { name: "show_vip", selector: { boolean: {} } },
];

class FritzboxAnrufeCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = withDefaults(config);
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _valueChanged(ev) {
    ev.stopPropagation();
    this._config = ev.detail.value;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => this._valueChanged(ev));
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = EDITOR_SCHEMA;
    this._form.computeLabel = computeEditorLabel;
  }
}

customElements.define("fritzbox-anrufe-card", FritzboxAnrufeCard);
customElements.define("fritzbox-anrufe-card-editor", FritzboxAnrufeCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "fritzbox-anrufe-card",
  name: "FRITZ!Box Anrufe",
  description:
    "Zeigt eingehende, ausgehende und verpasste FRITZ!Box-Anrufe als filterbare Liste inkl. Live-Anzeige und Anrufbeantworter - jede Kategorie einzeln ein-/ausblendbar.",
});
