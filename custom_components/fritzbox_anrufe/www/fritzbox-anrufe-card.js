/**
 * fritzbox-anrufe-card
 * ---------------------
 * Custom Lovelace card for the fritzbox_anrufe Home Assistant integration.
 *
 * Shows a filterable list of incoming/outgoing/missed FRITZ!Box calls with
 * an icon bar (Alle / Eingehend / Ausgehend / Verpasst) to switch between
 * them, plus a live-call banner above the icons whenever a call is
 * currently ringing/dialing/ongoing. Responsive: the layout stays legible
 * on both a phone-width and a desktop-width dashboard.
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
 *   max_rows: 10
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
    this._config = {
      title: "FRITZ!Box Anrufe",
      max_rows: 10,
      ...config,
    };
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

  static getStubConfig(hass, entities) {
    const guess = (suffix) =>
      (entities || []).find((e) => e.startsWith("sensor.") && e.includes(suffix)) || "";
    return {
      entity_live: guess("call_monitor") || guess("live"),
      entity_eingehend: guess("eingehend"),
      entity_ausgehend: guess("ausgehend"),
      entity_verpasst: guess("verpasst"),
      max_rows: 10,
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

  _liveStateObj() {
    return this._entityState(this._config.entity_live);
  }

  _isLiveActive() {
    const stateObj = this._liveStateObj();
    return !!stateObj && !LIVE_INACTIVE_STATES.has(stateObj.state);
  }

  _formatDate(iso) {
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

  _typeIcon(type) {
    return (FILTER_META[type] && FILTER_META[type].icon) || "mdi:phone";
  }

  _escape(value) {
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
          <span class="live-state">${this._escape(label)}</span>
          <span class="live-detail">${this._escape(name)}${separator}${this._escape(number)}</span>
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
              title="${this._escape(meta.label)}"
            >
              <ha-icon icon="${meta.icon}"></ha-icon>
              <span>${this._escape(meta.label)}</span>
            </button>
          `;
        }).join("")}
      </div>
    `;
  }

  _renderRows() {
    const calls = this._visibleCalls();
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
                <span class="row-name">${this._escape(call.name || call.number || "Unbekannt")}</span>
                ${call.vip ? '<ha-icon class="vip" icon="mdi:star"></ha-icon>' : ""}
              </div>
              <div class="row-secondary">
                <span class="row-number">${this._escape(call.number || "")}</span>
                <span class="row-date">${this._formatDate(call.date)}</span>
              </div>
            </div>
            <div class="row-extra">
              ${call.duration ? `<span class="row-duration">${this._escape(call.duration)}</span>` : ""}
              ${call.device ? `<span class="row-device">${this._escape(call.device)}</span>` : ""}
            </div>
          </div>
        `
          )
          .join("")}
      </div>
    `;
  }

  _render() {
    if (!this._config || !this._hass) return;

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card header="${this._escape(this._config.title)}">
        <div class="card-content">
          ${this._renderLiveBanner()}
          ${this._renderTabs()}
          ${this._renderRows()}
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
      .row-number { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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

customElements.define("fritzbox-anrufe-card", FritzboxAnrufeCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "fritzbox-anrufe-card",
  name: "FRITZ!Box Anrufe",
  description:
    "Zeigt eingehende, ausgehende und verpasste FRITZ!Box-Anrufe als filterbare Liste inkl. Live-Anzeige.",
});
