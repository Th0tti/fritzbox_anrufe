/**
 * fritzbox-anrufe-card
 * ---------------------
 * Custom Lovelace card for the fritzbox_anrufe Home Assistant integration.
 *
 * Shows a filterable list of incoming/outgoing/missed FRITZ!Box calls plus
 * Anrufbeantworter (answering machine) messages, switched via a 5-icon
 * header bar (Alle / Angenommen / Ausgehend / Verpasst / Anrufbeantworter -
 * Anrufbeantworter is a tab like the others, not a separate section below
 * the call list), with a live-call banner above the icons whenever a call
 * is currently ringing/dialing/ongoing. Responsive: the layout stays
 * legible on both a phone-width and a desktop-width dashboard.
 *
 * The "eingehend"/incoming filter/config key (internal identifier, unique_id
 * and entity_id all stay "eingehend" for backwards compatibility - see
 * const.py:CALL_TYPE_INCOMING) is labeled "Angenommen" in the UI since
 * v1.0.3: after that version's reclassification (calls routed to the
 * answering machine now count as "verpasst"), this tab only ever contains
 * calls a person actually answered, so "Eingehend" read as misleading -
 * per Thorsten.
 *
 * Every category - Alle/Gesamt, Angenommen, Ausgehend, Verpasst and
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
 * configuration still works. Since v1.0.4, the editor groups its many
 * settings into collapsible sections (Sensoren/Kategorien/Darstellung/
 * Weiterverarbeitung/Farben) via <ha-form>'s "expandable" schema type with
 * `flatten: true` - the resulting config stays a flat object (identical
 * YAML keys as before), the grouping is purely visual. This relies on a
 * reasonably recent Home Assistant frontend; NOT confirmed against real
 * hardware/every HA version - please open a GitHub issue if the editor
 * renders oddly (e.g. ungrouped, or with a stray top-level key) on your
 * instance.
 *
 * Since v1.0.4, most icon/symbol colors are also configurable (editor
 * group "Farben", `color_*` config keys below) - each accepts a CSS color
 * value (hex, rgb()/rgba(), hsl(), or a CSS variable reference) and falls
 * back to the previous hard-coded theme-color default when left empty, so
 * existing dashboards render unchanged unless a color is explicitly set.
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
 * "Weiterverarbeitung" (since v1.0.3, optional, off by default): an extra
 * status row per call, shown beneath its normal row when the matching
 * show_processing_* toggle is on. Shows how the call was resolved
 * (call.outcome, computed server-side - see call_log.py:_classify_call)
 * as an arrow + icon. For eingehend/ausgehend/verpasst it links to that
 * outcome's most relevant tab (e.g. a "verpasst" entry with a recorded
 * message links to "Anrufbeantworter"); for a recorded message it instead
 * plays the recording directly, inline, the same way the Anrufbeantworter
 * tab's own "Abspielen" button does. show_processing_alle controls the
 * same row on the combined "Alle" tab independently of the three
 * per-category toggles. See PROCESSING_META below for the exact
 * icon/label/target mapping, and the README's Fehlerbehebung section for
 * known limitations (the FRITZ!Box call list cannot reliably distinguish
 * "besetzt" from "niemand nimmt ab", nor "vor dem Anrufbeantworter
 * aufgelegt" from "Anrufbeantworter erreicht, aber keine Nachricht
 * hinterlassen" - both pairs collapse into one shared outcome each for
 * now).
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
 *   show_processing_alle: false
 *   show_processing_eingehend: false
 *   show_processing_ausgehend: false
 *   show_processing_verpasst: false
 *   color_tab_active: ""
 *   color_success: ""
 *   color_error: ""
 *   color_playback: ""
 *   color_vip: ""
 *   color_row_icon: ""
 *   color_live_banner: ""
 */

const FILTER_ALL = "alle";
const FILTER_VOICEMAIL = "anrufbeantworter";
// "anrufbeantworter" is a tab like any other (5th icon in the header row),
// not a section rendered underneath the call list - see _renderMainContent().
const FILTER_ORDER = ["alle", "eingehend", "ausgehend", "verpasst", FILTER_VOICEMAIL];

const FILTER_META = {
  alle: { icon: "mdi:phone-log", label: "Alle" },
  // Label "Angenommen" since v1.0.3 (was "Eingehend") - see the module
  // docstring above. The filter/config key itself stays "eingehend".
  eingehend: { icon: "mdi:phone-incoming", label: "Angenommen" },
  ausgehend: { icon: "mdi:phone-outgoing", label: "Ausgehend" },
  verpasst: { icon: "mdi:phone-missed", label: "Verpasst" },
  anrufbeantworter: { icon: "mdi:voicemail", label: "Anrufbeantworter" },
};

const LIVE_STATE_LABELS = {
  ringing: "Klingelt",
  dialing: "Wählen",
  talking: "Gespräch läuft",
};

// Allowlist, not a denylist: the banner must only ever appear for the three
// known "call in progress" states. A denylist of merely "known-inactive"
// values (idle/unavailable/unknown/"") looked equivalent at first glance,
// but silently broke down whenever entity_live pointed at the wrong entity
// (e.g. a *count* sensor such as the Anrufbeantworter-Sensor, whose native
// state is an integer like "10") - any value not on that denylist was
// treated as an active call and rendered verbatim as the banner text. With
// an allowlist, a misconfigured or unexpected state simply hides the
// banner instead of displaying garbage.
const LIVE_ACTIVE_STATES = new Set(Object.keys(LIVE_STATE_LABELS));

// "Weiterverarbeitung"-Zeile (seit v1.0.3, siehe Moduldoku oben): Zuordnung
// call.outcome (server-seitig berechnet, siehe call_log.py:_classify_call)
// -> Icon/Beschriftung/Farb-Kategorie/Ziel-Tab. "playable" statt "tab":
// Klick spielt die verlinkte Aufnahme direkt ab, statt nur den Tab zu
// wechseln - siehe _renderProcessingRow()/playCallRecording().
//
// "colorKind" (seit v1.0.4, statt einer festen Farbe direkt hier): verweist
// auf eine der drei benutzerdefinierbaren Farbgruppen aus PROCESSING_COLOR_VARS
// unten (success/error/playback) - siehe dort für die tatsächliche CSS-
// Custom-Property samt Standardwert, und den Editor-Bereich "Farben" für
// die Konfigurationsoberfläche.
const PROCESSING_META = {
  beantwortet: {
    icon: "mdi:phone-check",
    label: "Angenommen",
    colorKind: "success",
    tab: "eingehend",
  },
  verbunden: {
    icon: "mdi:phone-check",
    label: "Verbunden",
    colorKind: "success",
    tab: "ausgehend",
  },
  nicht_verbunden: {
    icon: "mdi:phone-remove",
    label: "Nicht verbunden",
    colorKind: "error",
    tab: "ausgehend",
  },
  nicht_erreicht: {
    icon: "mdi:phone-missed",
    label: "Nicht erreicht",
    colorKind: "error",
    tab: "verpasst",
  },
  // Ging zum Anrufbeantworter, aber es wurde keine Nachricht hinterlassen -
  // seit v1.0.3 getrennt von "nicht_erreicht" (siehe const.py:
  // CALL_OUTCOME_NO_VOICEMAIL), da der Anruf den Anrufbeantworter ja
  // tatsächlich erreicht hat, nur eben ohne Sprachnachricht - per Thorsten
  // war "Nicht erreicht" dafür irreführend.
  keine_nachricht: {
    icon: "mdi:phone-missed",
    label: "Keine Anrufbeantworter-Nachricht vorhanden",
    colorKind: "error",
    tab: "verpasst",
  },
  anrufbeantworter: {
    icon: "mdi:play-circle-outline",
    label: "Anrufbeantworter-Nachricht abspielen",
    colorKind: "playback",
    tab: "anrufbeantworter",
    playable: true,
  },
};

// --- Konfigurierbare Farben (seit v1.0.4) -----------------------------
//
// Jede Farbgruppe entspricht einer CSS-Custom-Property, die _colorVars()
// pro Karteninstanz auf Basis der Konfiguration (config-Schlüssel gleichen
// Namens) setzt - leer/nicht gesetzt lässt den bisherigen, festen
// Theme-Farbwert unverändert (siehe DEFAULT dort). PROCESSING_COLOR_VARS
// bildet den obigen "colorKind" auf die jeweilige CSS-Variable ab.
const COLOR_CONFIG_KEYS = {
  tab_active: { cssVar: "--fba-color-tab-active", fallback: "var(--primary-color, #03a9f4)" },
  success: { cssVar: "--fba-color-success", fallback: "var(--success-color, #4caf50)" },
  error: { cssVar: "--fba-color-error", fallback: "var(--error-color, #db4437)" },
  playback: { cssVar: "--fba-color-playback", fallback: "var(--primary-color, #03a9f4)" },
  vip: { cssVar: "--fba-color-vip", fallback: "var(--warning-color, #ff9800)" },
  row_icon: { cssVar: "--fba-color-row-icon", fallback: "var(--secondary-text-color, #727272)" },
  live_banner: {
    cssVar: "--fba-color-live-banner",
    fallback: "var(--state-icon-active-color, #03a9f4)",
  },
};

const PROCESSING_COLOR_VARS = {
  success: "var(--fba-color-success)",
  error: "var(--fba-color-error)",
  playback: "var(--fba-color-playback)",
};

// Defensive allowlist for user-supplied color values before they land
// inside a <style> block (via innerHTML, see _render()): permits hex
// codes, rgb()/rgba()/hsl()/hsla(), CSS variable references
// (var(--name, fallback)) and plain color-word characters, but rejects
// anything containing characters that could break out of the custom
// property declaration or the <style> tag itself (";", "{", "}", "<",
// ">", quotes, ...). An invalid value is treated the same as "not set"
// (falls back to the theme default) rather than raising an error, since
// this runs on every render.
const SAFE_COLOR_RE = /^[a-zA-Z0-9#(),.%\-\s]+$/;

function sanitizeColor(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";
  if (!SAFE_COLOR_RE.test(trimmed)) {
    // eslint-disable-next-line no-console
    console.warn(
      "fritzbox_anrufe: ungültiger Farbwert ignoriert (nur Hex/rgb()/hsl()/var()/CSS-Farbnamen" +
        " erlaubt):",
      value
    );
    return "";
  }
  return trimmed;
}

const CONFIG_DEFAULTS = {
  title: "FRITZ!Box Anrufe",
  max_rows: 10,
  // Kategorien/Tabs (Alle/Gesamt, Angenommen, Ausgehend, Verpasst,
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
  // "Weiterverarbeitung"-Zeile je Kategorie einzeln ein-/ausblendbar -
  // standardmäßig aus, damit bestehende Dashboards nach einem Update
  // optisch unverändert bleiben (siehe Moduldoku oben).
  show_processing_alle: false,
  show_processing_eingehend: false,
  show_processing_ausgehend: false,
  show_processing_verpasst: false,
  // Farben (seit v1.0.4) - leer = bisheriger, fester Theme-Farbwert (siehe
  // COLOR_CONFIG_KEYS oben für die jeweiligen Standardwerte).
  color_tab_active: "",
  color_success: "",
  color_error: "",
  color_playback: "",
  color_vip: "",
  color_row_icon: "",
  color_live_banner: "",
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
  /* container-type/-name (seit v1.0.4): lässt die Tab-Leiste unten auf die
     tatsächliche Breite DIESER KARTE reagieren statt auf die Browser-
     Fensterbreite (siehe TABS_CONTAINER_QUERY_STYLES unten für den Grund -
     das bestehende @media-Breakpoint für Smartphones griff auf einer
     schmalen Desktop-Dashboard-Spalte nie, weil der Browser selbst breit
     genug war). Modernes CSS-Feature (Container Queries) - falls der
     Browser es nicht unterstützt, greift ersatzweise nur die
     min-width/ellipsis-Absicherung direkt an .tab/.tab span, die
     Kategorie-Leiste läuft dann nie in einen Scrollbalken, kann aber
     Beschriftungen abschneiden statt komplett auf Icons umzuschalten. */
  .card-content { padding: 8px 16px 16px; container-type: inline-size; container-name: fba; }
  .empty {
    padding: 24px 0;
    text-align: center;
    color: var(--secondary-text-color, #727272);
  }
`;

// Schwelle empirisch ermittelt (siehe PR-Beschreibung/Commit): bei den fünf
// Tabs "Alle"/"Angenommen"/"Ausgehend"/"Verpasst"/"Anrufbeantworter" passt
// der volle Text ab ca. 488px Innenbreite der Karte ohne jede Kürzung -
// darunter wird auf reine Icons umgeschaltet (mit Tooltip via title="...",
// siehe _renderTabs()), statt Labels hässlich mitten im Wort abzuschneiden.
const TABS_CONTAINER_QUERY_STYLES = `
  @container fba (max-width: 480px) {
    .tab span { display: none; }
    .tab ha-icon { --mdc-icon-size: 22px; }
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
  .voicemail-row.unread { border-left: 3px solid var(--fba-color-playback); }
  .voicemail-main { display: flex; flex-direction: column; gap: 2px; }
  .voicemail-primary { display: flex; align-items: center; gap: 6px; }
  .voicemail-name { font-weight: 500; }
  .voicemail-badge {
    font-size: 0.7em;
    text-transform: uppercase;
    background: var(--fba-color-playback);
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
    background: var(--fba-color-playback);
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

// --- "Weiterverarbeitung"-Zeile (seit v1.0.3) --------------------------
const PROCESSING_ROW_STYLES = `
  .row-processing {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 2px 0 6px 30px;
    padding: 2px 8px;
    font-size: 0.8em;
    color: var(--secondary-text-color, #727272);
  }
  .row-processing.clickable {
    cursor: pointer;
    border-radius: 6px;
  }
  .row-processing.clickable:hover {
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
  }
  .row-processing-arrow { opacity: 0.6; }
  .row-processing ha-icon { --mdc-icon-size: 18px; }
  .row-processing-player { height: 28px; }
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

/**
 * Same idea as playVoicemail() above, but for a "Weiterverarbeitung" row
 * (see PROCESSING_META) linked from a call-list entry rather than the
 * Anrufbeantworter tab's own message list - reuses the identical
 * hass.fetchWithAuth()-to-blob-object-URL approach, just swapping the
 * *whole* row's content (arrow+icon+label) for the <audio> element instead
 * of a dedicated player slot next to a button.
 */
async function playCallRecording(hass, rowEl, onObjectUrlCreated) {
  const mediaUrl = rowEl.dataset.mediaUrl;
  if (!mediaUrl || !hass || !hass.fetchWithAuth) return;

  rowEl.classList.remove("clickable");
  rowEl.innerHTML = `<ha-icon icon="mdi:loading"></ha-icon><span>Lädt …</span>`;

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
    audio.className = "row-processing-player";
    audio.src = objectUrl;
    rowEl.replaceChildren(audio);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("fritzbox_anrufe: Wiedergabe über die Weiterverarbeitungs-Zeile fehlgeschlagen", err);
    rowEl.classList.add("clickable");
    rowEl.innerHTML = `<ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>Fehler – erneut versuchen</span>`;
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
    return !!stateObj && LIVE_ACTIVE_STATES.has(stateObj.state);
  }

  _typeIcon(type) {
    return (FILTER_META[type] && FILTER_META[type].icon) || "mdi:phone";
  }

  // Ob die "Weiterverarbeitung"-Zeile für einen Anruf des gegebenen
  // Anruflisten-Typs gezeigt werden soll. Auf der "Alle"-Sammelansicht
  // entscheidet ausschließlich show_processing_alle (Punkt 6) - unabhängig
  // vom eigentlichen Typ des jeweiligen Anrufs; auf einer einzelnen
  // Kategorie-Ansicht (eingehend/ausgehend/verpasst) der jeweils passende
  // show_processing_<typ>-Schalter (Punkte 3-5).
  _processingEnabledFor(callType) {
    if (this._activeFilter === FILTER_ALL) {
      return !!this._config.show_processing_alle;
    }
    return !!this._config[`show_processing_${callType}`];
  }

  _renderProcessingRow(call) {
    if (!this._processingEnabledFor(call.type)) return "";
    const meta = PROCESSING_META[call.outcome];
    // Kein bekannter/gemappter outcome (z. B. noch nicht aktualisierter
    // Sensor-Zustand vor einem Neustart nach dem Update) - Zeile einfach
    // weglassen statt ein kaputtes Icon zu zeigen.
    if (!meta) return "";

    const canPlay = !!(meta.playable && call.media_url);
    const attrs = [
      canPlay ? `data-media-url="${escapeHtml(call.media_url)}"` : "",
      meta.tab ? `data-target-tab="${escapeHtml(meta.tab)}"` : "",
    ]
      .filter(Boolean)
      .join(" ");
    const clickable = canPlay || !!meta.tab;

    const color = PROCESSING_COLOR_VARS[meta.colorKind] || "inherit";
    return `
      <div class="row-processing ${clickable ? "clickable" : ""}" ${attrs} title="${escapeHtml(meta.label)}">
        <span class="row-processing-arrow" aria-hidden="true">↳</span>
        <ha-icon icon="${meta.icon}" style="color: ${color};"></ha-icon>
        <span class="row-processing-label">${escapeHtml(meta.label)}</span>
      </div>
    `;
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
          ${this._renderProcessingRow(call)}
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

    this.shadowRoot.querySelectorAll(".row-processing.clickable").forEach((row) => {
      row.addEventListener("click", () => {
        // Once playback has started the row holds a native <audio> element -
        // let its own controls handle further clicks instead of re-triggering.
        if (row.querySelector("audio")) return;
        if (row.dataset.mediaUrl) {
          playCallRecording(this._hass, row, (url) => this._objectUrls.push(url));
          return;
        }
        if (row.dataset.targetTab) {
          this._activeFilter = row.dataset.targetTab;
          this._lastSignature = this._computeSignature();
          this._render();
        }
      });
    });
  }

  // CSS-Custom-Property-Deklarationen für alle konfigurierbaren Farben
  // (seit v1.0.4) - ein leerer/nicht gesetzter config-Wert fällt auf den
  // bisherigen, festen Theme-Farbwert zurück (COLOR_CONFIG_KEYS), ein
  // ungültiger Wert wird von sanitizeColor() verworfen (ebenfalls Fallback).
  _colorVars() {
    const cfg = this._config || {};
    return Object.entries(COLOR_CONFIG_KEYS)
      .map(([key, { cssVar, fallback }]) => {
        const value = sanitizeColor(cfg[`color_${key}`]) || fallback;
        return `${cssVar}: ${value};`;
      })
      .join("\n        ");
  }

  _styles() {
    return `
      :host {
        ${this._colorVars()}
      }

      ${BASE_CARD_STYLES}

      .live-banner {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 12px;
        margin-bottom: 12px;
        border-radius: 8px;
        background: var(--fba-color-live-banner);
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
        /* min-width: 0 overrides the flexbox default of "min-width: auto"
           (= the label's un-wrapped content width), which is what let a
           tab's own label force the whole .tabs row wider than the card
           and trigger its horizontal scrollbar - most noticeably once
           "Eingehend" (v1.0.3) became the longer "Angenommen". With this,
           a tab can now shrink below its label's natural width; the label
           itself truncates with an ellipsis (see ".tab span" below)
           instead of forcing an overflow. */
        min-width: 0;
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
      .tab ha-icon { --mdc-icon-size: 20px; flex-shrink: 0; }
      .tab.active {
        color: var(--fba-color-tab-active);
        border-bottom-color: var(--fba-color-tab-active);
        font-weight: 600;
      }
      .tab span {
        font-size: 0.8em;
        overflow: hidden;
        text-overflow: ellipsis;
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
        color: var(--fba-color-row-icon);
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
      .vip { --mdc-icon-size: 14px; color: var(--fba-color-vip); }
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
      ${PROCESSING_ROW_STYLES}
      ${TABS_CONTAINER_QUERY_STYLES}

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
  entity_eingehend: "Sensor: Angenommene Anrufe",
  entity_ausgehend: "Sensor: Ausgehende Anrufe",
  entity_verpasst: "Sensor: Verpasste Anrufe",
  entity_voicemail: "Sensor: Anrufbeantworter (optional)",
  max_rows: "Max. Zeilen",
  show_alle: "Kategorie 'Gesamt' (Alle) anzeigen",
  show_eingehend: "Kategorie 'Angenommen' anzeigen",
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
  show_processing_alle: "Weiterverarbeitung auf 'Gesamt' anzeigen",
  show_processing_eingehend: "Weiterverarbeitung bei 'Angenommen' anzeigen",
  show_processing_ausgehend: "Weiterverarbeitung bei 'Ausgehend' anzeigen",
  show_processing_verpasst: "Weiterverarbeitung bei 'Verpasst' anzeigen",
  // Farben (seit v1.0.4) - siehe COLOR_CONFIG_KEYS/PROCESSING_COLOR_VARS
  // oben für die jeweils betroffenen Icons/Symbole.
  color_tab_active: "Farbe: aktiver Tab",
  color_success: "Farbe: erfolgreich (angenommen/verbunden)",
  color_error: "Farbe: nicht erfolgreich (nicht erreicht/nicht verbunden)",
  color_playback: "Farbe: Wiedergabe (Abspielen-Button, Anrufbeantworter-Symbol, 'Neu'-Markierung)",
  color_vip: "Farbe: VIP-Markierung",
  color_row_icon: "Farbe: Anruf-Symbole in der Liste",
  color_live_banner: "Farbe: Live-Banner-Hintergrund",
};

// Kurzer Hilfetext unter den Farbfeldern (ha-form's computeHelper, falls von
// der jeweiligen Home-Assistant-Frontend-Version unterstützt - andernfalls
// wird er schlicht ignoriert, siehe _renderConfig()).
const EDITOR_COLOR_HELPER =
  "CSS-Farbwert, z. B. #4caf50, rgb(76,175,80) oder ein Theme-Farbname wie" +
  " var(--accent-color) - leer lassen für die Standardfarbe.";

const EDITOR_HELPERS = {
  color_tab_active: EDITOR_COLOR_HELPER,
  color_success: EDITOR_COLOR_HELPER,
  color_error: EDITOR_COLOR_HELPER,
  color_playback: EDITOR_COLOR_HELPER,
  color_vip: EDITOR_COLOR_HELPER,
  color_row_icon: EDITOR_COLOR_HELPER,
  color_live_banner: EDITOR_COLOR_HELPER,
};

function computeEditorLabel(schemaItem) {
  return EDITOR_LABELS[schemaItem.name] || schemaItem.name;
}

function computeEditorHelper(schemaItem) {
  return EDITOR_HELPERS[schemaItem.name] || "";
}

// Seit v1.0.4 in Abschnitte gruppiert (Home Assistant seit einiger Zeit als
// <ha-form>-Schema-Typ "expandable" verfügbar), damit der mittlerweile recht
// lange Editor übersichtlich bleibt - per Nutzerwunsch, nachdem die Liste
// der Einzelfelder unhandlich geworden war. "flatten: true" sorgt dafür,
// dass die Werte trotz der visuellen Gruppierung weiterhin als flaches
// Konfigurationsobjekt gespeichert werden (identische YAML-Schlüssel wie
// zuvor) - siehe Moduldoku oben für den Hinweis zur Versionsabhängigkeit.
const EDITOR_SCHEMA = [
  { name: "title", selector: { text: {} } },
  {
    name: "",
    type: "expandable",
    title: "Sensoren",
    icon: "mdi:radar",
    flatten: true,
    expanded: true,
    schema: [
      { name: "entity_live", selector: { entity: { domain: "sensor" } } },
      { name: "entity_eingehend", selector: { entity: { domain: "sensor" } } },
      { name: "entity_ausgehend", selector: { entity: { domain: "sensor" } } },
      { name: "entity_verpasst", selector: { entity: { domain: "sensor" } } },
      { name: "entity_voicemail", selector: { entity: { domain: "sensor" } } },
    ],
  },
  {
    name: "",
    type: "expandable",
    title: "Kategorien",
    icon: "mdi:filter-variant",
    flatten: true,
    expanded: false,
    schema: [
      { name: "show_alle", selector: { boolean: {} } },
      { name: "show_eingehend", selector: { boolean: {} } },
      { name: "show_ausgehend", selector: { boolean: {} } },
      { name: "show_verpasst", selector: { boolean: {} } },
      { name: "show_anrufbeantworter", selector: { boolean: {} } },
    ],
  },
  {
    name: "",
    type: "expandable",
    title: "Darstellung",
    icon: "mdi:table-column",
    flatten: true,
    expanded: false,
    schema: [
      // "slider" statt "box": das Zahlenfeld ("box") ließ sich bei manchen
      // Nutzern nicht zuverlässig per Tastatur bearbeiten (Eingaben wurden
      // teils zurückgesetzt) - ein Schieberegler kommt komplett ohne
      // Texteingabe aus und umgeht das Problem. Wer mehr als 15 Zeilen
      // braucht, kann max_rows weiterhin über den YAML-Editor der Karte auf
      // einen beliebigen Wert setzen.
      { name: "max_rows", selector: { number: { min: 1, max: 15, step: 1, mode: "slider" } } },
      { name: "show_name", selector: { boolean: {} } },
      { name: "show_number", selector: { boolean: {} } },
      { name: "show_own_number", selector: { boolean: {} } },
      { name: "show_device", selector: { boolean: {} } },
      { name: "show_duration", selector: { boolean: {} } },
      { name: "show_date", selector: { boolean: {} } },
      { name: "show_vip", selector: { boolean: {} } },
    ],
  },
  {
    name: "",
    type: "expandable",
    title: "Weiterverarbeitung",
    icon: "mdi:arrow-decision-outline",
    flatten: true,
    expanded: false,
    schema: [
      { name: "show_processing_alle", selector: { boolean: {} } },
      { name: "show_processing_eingehend", selector: { boolean: {} } },
      { name: "show_processing_ausgehend", selector: { boolean: {} } },
      { name: "show_processing_verpasst", selector: { boolean: {} } },
    ],
  },
  {
    name: "",
    type: "expandable",
    title: "Farben",
    icon: "mdi:palette-outline",
    flatten: true,
    expanded: false,
    schema: [
      { name: "color_tab_active", selector: { text: {} } },
      { name: "color_success", selector: { text: {} } },
      { name: "color_error", selector: { text: {} } },
      { name: "color_playback", selector: { text: {} } },
      { name: "color_vip", selector: { text: {} } },
      { name: "color_row_icon", selector: { text: {} } },
      { name: "color_live_banner", selector: { text: {} } },
    ],
  },
];

class FritzboxAnrufeCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = withDefaults(config);
    this._renderConfig();
  }

  set hass(hass) {
    this._hass = hass;
    // IMPORTANT: only refresh the form's `hass` reference here (needed so
    // e.g. entity pickers see current entity state/translations) - do NOT
    // also reset `.data` on every hass tick. Home Assistant pushes a new
    // hass object to every card/editor on ANY entity state change system-
    // wide, completely unrelated to this form; re-assigning `.data` each
    // time reset the underlying <ha-form> number/text inputs mid-edit,
    // which made it look like a value (e.g. typing "5" over "10") could
    // never "stick" - every keystroke got wiped by the next hass update
    // before the user could finish. `.data` is now only set from
    // setConfig()/_renderConfig() - i.e. on genuine external config
    // changes, not on unrelated background hass churn.
    if (this._form) {
      this._form.hass = hass;
    } else {
      this._renderConfig();
    }
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

  _renderConfig() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => this._valueChanged(ev));
      this._form.schema = EDITOR_SCHEMA;
      this._form.computeLabel = computeEditorLabel;
      // computeHelper is a newer <ha-form> hook (short description text
      // under a field); if the running frontend version doesn't support it,
      // it's simply never called - safe to always set.
      this._form.computeHelper = computeEditorHelper;
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
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
