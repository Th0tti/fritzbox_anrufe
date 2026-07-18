/**
 * fritzbox-anrufe-card
 * ---------------------
 * Custom Lovelace card for the fritzbox_anrufe Home Assistant integration.
 *
 * Shows a filterable list of incoming/outgoing/missed FRITZ!Box calls with
 * an icon bar (Alle / Eingehend / Ausgehend / Verpasst) to switch between
 * them, a live-call banner above the icons whenever a call is currently
 * ringing/dialing/ongoing, and an optional Anrufbeantworter (answering
 * machine) section with inline playback. Responsive: the layout stays
 * legible on both a phone-width and a desktop-width dashboard.
 *
 * Includes a graphical config editor (via getConfigElement) to pick the
 * entities, the row count, and which call attributes/columns are shown -
 * no YAML editing required, though YAML configuration still works.
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
 *   show_name: true
 *   show_number: true
 *   show_own_number: false
 *   show_device: true
 *   show_duration: true
 *   show_date: true
 *   show_vip: true
 */

const FILTER_ALL = "alle";
const FILTER_ORDER = ["alle", "eingehend", "ausgehend", "verpasst"];

const FILTER_META = {
  alle: { icon: "mdi:phone-log", label: "Alle" },
  eingehend: { icon: "mdi:phone-incoming", label: "Eingehend" },
  ausgehend: { icon: "mdi:phone-outgoing", label: "Ausgehend" },
  verpasst: { icon: "mdi:phone-missed", label: "Verpasst" },
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

class FritzboxAnrufeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._activeFilter = FILTER_ALL;
    this._hass = null;
    this._config = null;
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
    this._activeFilter = FILTER_ALL;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
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
      const combined = ["eingehend", "ausgehend", "verpasst"].flatMap((type) =>
        this._callsFor(type)
      );
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
    return `
      <div class="tabs" role="tablist">
        ${FILTER_ORDER.map((type) => {
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
        }).join("")}
      </div>
    `;
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

  _renderVoicemailSection() {
    if (!this._config.entity_voicemail) return "";
    const messages = this._voicemails();
    return `
      <div class="voicemail-section">
        <div class="voicemail-header">
          <ha-icon icon="mdi:voicemail"></ha-icon>
          <span>Anrufbeantworter</span>
        </div>
        ${
          messages.length
            ? `<div class="voicemail-rows">
                ${messages
                  .map(
                    (msg) => `
                  <div class="voicemail-row ${msg.new ? "unread" : ""}">
                    <div class="voicemail-main">
                      <div class="voicemail-primary">
                        <span class="voicemail-name">${escapeHtml(msg.name || msg.number || "Unbekannt")}</span>
                        ${msg.new ? '<span class="voicemail-badge">neu</span>' : ""}
                      </div>
                      <div class="voicemail-secondary">
                        <span>${escapeHtml(msg.number || "")}</span>
                        <span>${formatDateTime(msg.date)}</span>
                        ${msg.duration ? `<span>${escapeHtml(msg.duration)}</span>` : ""}
                      </div>
                    </div>
                    ${
                      msg.media_url
                        ? `<audio class="voicemail-player" controls preload="none" src="${escapeHtml(msg.media_url)}"></audio>`
                        : `<span class="voicemail-no-audio">Kein Wiedergabelink</span>`
                    }
                  </div>
                `
                  )
                  .join("")}
              </div>`
            : `<div class="empty">Keine Nachrichten vorhanden.</div>`
        }
      </div>
    `;
  }

  _render() {
    if (!this._config || !this._hass) return;

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card header="${escapeHtml(this._config.title)}">
        <div class="card-content">
          ${this._renderLiveBanner()}
          ${this._renderTabs()}
          ${this._renderRows()}
          ${this._renderVoicemailSection()}
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._activeFilter = btn.dataset.filter;
        this._render();
      });
    });
  }

  _styles() {
    return `
      ha-card { overflow: hidden; }
      .card-content { padding: 8px 16px 16px; }

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

      .empty {
        padding: 24px 0;
        text-align: center;
        color: var(--secondary-text-color, #727272);
      }

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

      .voicemail-section {
        margin-top: 16px;
        padding-top: 12px;
        border-top: 1px solid var(--divider-color, #e0e0e0);
      }
      .voicemail-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        font-weight: 600;
        color: var(--primary-text-color);
      }
      .voicemail-rows { display: flex; flex-direction: column; gap: 10px; }
      .voicemail-row {
        display: flex;
        flex-direction: column;
        gap: 4px;
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
      .voicemail-player { width: 100%; height: 32px; margin-top: 2px; }
      .voicemail-no-audio {
        font-size: 0.8em;
        color: var(--secondary-text-color, #727272);
        font-style: italic;
      }

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
    "Zeigt eingehende, ausgehende und verpasste FRITZ!Box-Anrufe als filterbare Liste inkl. Live-Anzeige und Anrufbeantworter.",
});
