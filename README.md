# FRITZ!Box Anrufe

Home-Assistant-Integration für den Anrufmonitor und die Anruflisten (eingehend,
ausgehend, verpasst) einer AVM FRITZ!Box. Basiert auf der in Home Assistant
integrierten "FRITZ!Box Call Monitor"-Komponente, erweitert um historische
Anruflisten-Sensoren, konfigurierbare Verlaufstiefe je Sensor und eine
mitgelieferte Dashboard-Karte.

## Inhalt

- [Funktionsumfang](#funktionsumfang)
- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Einrichtung](#einrichtung)
- [Sensoren](#sensoren)
- [Einstellungen (Optionen)](#einstellungen-optionen)
- [Dashboard-Karte](#dashboard-karte)
- [Icon](#icon)
- [Bekannte Einschränkungen](#bekannte-einschränkungen)
- [Versionshistorie](#versionshistorie)
- [Fehlerbehebung](#fehlerbehebung)

## Funktionsumfang

- Live-Anrufmonitor (klingelt/wählt/spricht/inaktiv) in Echtzeit über den
  FRITZ!Box-Callmonitor (TCP-Port 1012), wie bei der Kernintegration.
- Drei zusätzliche Sensoren für die Anruflisten: eingehend, ausgehend,
  verpasst - inklusive Anrufer-/Angerufener-Name (aus dem Telefonbuch),
  Nummer, Zeitpunkt, Dauer und Gerät je Anruf.
- Verlaufstiefe je Sensor unabhängig einstellbar (Anzahl der Anrufe ODER
  Anzahl Tage), bereits bei der Erst-Einrichtung und jederzeit später über
  die Integrations-Optionen änderbar.
- Mitgelieferte, interaktive Dashboard-Karte (`fritzbox-anrufe-card`) mit
  Icon-Filterleiste, Live-Banner und responsivem Layout - keine manuelle
  Lovelace-Ressource nötig.
- Grafischer Karten-Editor (Home-Assistant-Standardformular): Sensoren,
  Zeilenanzahl und einzeln zuschaltbare Spalten (Name, Nummer, eigene
  Rufnummer, Gerät, Dauer, Datum, VIP) lassen sich ohne YAML einstellen.
- **Experimentell:** Anrufbeantworter-Sensor mit Nachrichtenliste und
  abspielbaren Sprachnachrichten direkt im Dashboard (siehe
  [Bekannte Einschränkungen](#bekannte-einschränkungen) - bislang nicht an
  echter Hardware getestet).
- Alternative: einfache YAML-Tabellenkarte auf Basis von `flex-table-card`
  (siehe [`examples/dashboard_flex_table.yaml`](examples/dashboard_flex_table.yaml)).

## Voraussetzungen

- Eine AVM FRITZ!Box mit aktiviertem Callmonitor
  (`#96*5*` auf einem angeschlossenen Telefon wählen, um ihn zu aktivieren)
  und aktiviertem TR-064-Zugriff (FRITZ!Box-Oberfläche → Heimnetz →
  Netzwerk → Netzwerkeinstellungen → "Zugriff für Anwendungen zulassen").
- Ein FRITZ!Box-Benutzerkonto mit den Berechtigungen "FRITZ!Box-Einstellungen"
  sowie **"Sprachnachrichten, Faxnachrichten, FRITZ!App Fon und Anrufliste"**
  (System → FRITZ!Box-Benutzer → Berechtigungen). Ohne die zweite
  Berechtigung bleiben nur die drei Verlaufs-Sensoren `unavailable`, der
  Live-Sensor funktioniert davon unabhängig.
- Home Assistant, aktuelle Version empfohlen (getestet mit Python 3.14+,
  wie von aktuellen Home-Assistant-Releases vorausgesetzt).

## Installation

### Über HACS (empfohlen)

1. HACS → Integrationen → drei Punkte oben rechts → "Benutzerdefinierte
   Repositories" → URL `https://github.com/Th0tti/fritzbox_anrufe`,
   Kategorie "Integration" hinzufügen (falls das Repository nicht bereits
   als Standard-Repository gelistet ist).
2. "FRITZ!Box Anrufe" suchen und herunterladen.
3. Home Assistant **vollständig neu starten** (nicht nur neu laden).

### Manuell

1. Den Ordner `custom_components/fritzbox_anrufe` aus diesem Repository nach
   `<Home-Assistant-Konfigurationsverzeichnis>/custom_components/fritzbox_anrufe`
   kopieren.
2. Home Assistant vollständig neu starten.

## Einrichtung

1. Einstellungen → Geräte & Dienste → "+ Integration hinzufügen" →
   "FRITZ!Box Anrufe" suchen.
2. Zugangsdaten eingeben: Host/IP, Port (Standard 1012 für den Callmonitor),
   Benutzername, Passwort des oben genannten FRITZ!Box-Kontos.
3. Falls mehrere Telefonbücher vorhanden sind: gewünschtes Telefonbuch
   auswählen.
4. **Verlaufstiefe festlegen**: Für jeden der drei Anruflisten-Sensoren
   (eingehend/ausgehend/verpasst) getrennt auswählen, ob er nach *Anzahl*
   oder nach *Tagen* begrenzt werden soll, und den jeweiligen Wert per
   Dropdown wählen. Standardwert, falls nichts geändert wird: **10 Anrufe**
   je Sensor. Diese Einstellung lässt sich später jederzeit unter
   "Konfigurieren" wieder ändern (siehe [Einstellungen](#einstellungen-optionen)).

## Sensoren

Pro konfiguriertem Telefonbuch/FRITZ!Box-Konto werden fünf Sensoren angelegt:

| Sensor (Übersetzungsschlüssel) | Beschreibung | Zustand | Attribut |
| --- | --- | --- | --- |
| `fritzbox_anrufe_live` | Live-Anrufmonitor | `idle` / `ringing` / `dialing` / `talking` | - (siehe Live-Attribute unten) |
| `fritzbox_anrufe_eingehend` | Eingehende Anrufe | Anzahl gespeicherter Anrufe | `calls`: Liste eingehender Anrufe |
| `fritzbox_anrufe_ausgehend` | Ausgehende Anrufe | Anzahl gespeicherter Anrufe | `calls`: Liste ausgehender Anrufe |
| `fritzbox_anrufe_verpasst` | Verpasste Anrufe | Anzahl gespeicherter Anrufe | `calls`: Liste verpasster Anrufe |
| `fritzbox_anrufe_anrufbeantworter` **(experimentell)** | Anrufbeantworter-Nachrichten | Anzahl gespeicherter Nachrichten | `messages`: Liste der Sprachnachrichten |

Die Verlaufs- und der Anrufbeantworter-Sensor werden **nicht** über den
Callmonitor befüllt, sondern alle 5 Minuten per TR-064 von der FRITZ!Box
abgerufen (`X_AVM-DE_OnTel`/`GetCallList` bzw. `X_AVM-DE_TAM1`/
`GetMessageList`) - der Callmonitor liefert nur Live-Ereignisse, keine
Historie.

Jeder Eintrag in `calls` enthält: `type`, `date` (ISO-Zeitstempel), `name`
(aus dem Telefonbuch oder vom FRITZ!Box-Anruflisteneintrag), `number`,
`own_number`, `device`, `duration`, `vip` (Telefonbuch-Kategorie "wichtig").

Der Live-Sensor liefert je nach Zustand u. a. `from`/`to`/`with`,
`from_name`/`to_name`/`with_name`, `device`, `duration`, `vip`.

Jeder Eintrag in `messages` (Anrufbeantworter, experimentell) enthält:
`name`, `number`, `date` (ISO-Zeitstempel), `duration`, `new` (bool, ob die
Nachricht noch nicht abgehört wurde), `vip`, sowie `media_url` - eine
Home-Assistant-interne, authentifizierte URL, über die die Aufnahme direkt
im Browser abgespielt werden kann (siehe [Dashboard-Karte](#dashboard-karte)).

### Entity-IDs

Die Sensoren heißen intern `fritzbox_anrufe_live`/`_eingehend`/`_ausgehend`/
`_verpasst`/`_anrufbeantworter` (Übersetzungsschlüssel, steuert den je nach
Home-Assistant-Spracheinstellung übersetzten Anzeigenamen sowie das Icon).

Ab Version 1.0.1 wird zusätzlich die **technische entity_id** bei der
Ersteinrichtung fest auf genau diese Werte reserviert, z. B.
`sensor.fritzbox_anrufe_eingehend` (unabhängig von der Sprache, da
entity_ids in Home Assistant grundsätzlich sprachneutral bleiben sollen).
Das gilt für neu angelegte Entities; bereits vorhandene Entities aus einer
älteren Installation behalten ihre bisherige entity_id (Home Assistant
ändert bestehende entity_ids nie automatisch, um Automatisierungen nicht zu
brechen). Wer bei einem Bestandssystem auf die neuen, festen IDs wechseln
möchte: die fünf betroffenen Entities unter Einstellungen → Geräte &
Dienste → Entitäten einmalig löschen und die Integration danach neu laden
lassen - sie werden dann mit der festen entity_id neu angelegt. Bei mehr
als einem FRITZ!Box-Konto bekommt das zweite/dritte Konto automatisch die
Endungen `_2`/`_3` (normales Home-Assistant-Verhalten bei ID-Kollisionen).

## Einstellungen (Optionen)

Über Einstellungen → Geräte & Dienste → FRITZ!Box Anrufe → "Konfigurieren"
lassen sich jederzeit ändern:

- **Präfixe** (kommagetrennte Liste), zur Rufnummernauflösung z. B. bei
  abweichenden Landes-/Ortsvorwahlen im Telefonbuch.
- **Verlaufstiefe je Sensor** (eingehend/ausgehend/verpasst getrennt):
  - *Modus*: "Anzahl Anrufe" oder "Anzahl Tage".
  - *Anzahl*: Dropdown mit festen Werten 5 / 10 / 20 / 50 / 100 / 200
    (nur wirksam im Modus "Anzahl Anrufe").
  - *Tage*: Zahl zwischen 1 und 90 (nur wirksam im Modus "Anzahl Tage").

## Dashboard-Karte

### Variante 1: mitgelieferte Custom Card (empfohlen)

Ab Version 1.0.1 wird die Karte `fritzbox-anrufe-card` automatisch mit der
Integration ausgeliefert und registriert sich selbst als Lovelace-Ressource
(keine manuelle Einrichtung nötig - nur einmal Home Assistant neu starten,
nachdem die Integration installiert/aktualisiert wurde).

Funktionen:

- Icon-Leiste oben (Alle / Eingehend / Ausgehend / Verpasst) zum Filtern der
  Liste per Klick.
- Standardansicht "Alle" zeigt die neuesten Anrufe aller drei Typen gemischt
  (sortiert nach Datum), begrenzt auf `max_rows` Zeilen (Standard: 10).
- Findet gerade ein Gespräch statt (Live-Sensor ≠ "idle"), erscheint
  oberhalb der Icon-Leiste automatisch ein hervorgehobenes Live-Banner.
- **Experimentell:** Ist ein Anrufbeantworter-Sensor eingetragen, erscheint
  unterhalb der Anrufliste ein eigener "Anrufbeantworter"-Bereich mit einer
  Nachrichtenliste (Name/Nummer/Zeitpunkt/Dauer, neue Nachrichten farblich
  markiert) sowie einem `<audio>`-Player pro Nachricht zum direkten
  Abspielen im Dashboard - siehe den Hinweis dazu unter
  [Bekannte Einschränkungen](#bekannte-einschränkungen).
- Responsives Layout: auf schmalen Bildschirmen (Smartphone) werden
  Tab-Beschriftungen und die Geräte-Spalte ausgeblendet, Name/Nummer/Zeit
  bleiben immer sichtbar.

Beispielkonfiguration: [`examples/dashboard_custom_card.yaml`](examples/dashboard_custom_card.yaml).

```yaml
type: custom:fritzbox-anrufe-card
title: FRITZ!Box Anrufe
entity_live: sensor.fritz_box_7590_call_monitor
entity_eingehend: sensor.fritz_box_7590_eingehende_anrufe
entity_ausgehend: sensor.fritz_box_7590_ausgehende_anrufe
entity_verpasst: sensor.fritz_box_7590_verpasste_anrufe
entity_voicemail: sensor.fritz_box_7590_anrufbeantworter  # optional, experimentell
max_rows: 10
show_name: true
show_number: true
show_own_number: false
show_device: true
show_duration: true
show_date: true
show_vip: true
```

**Grafischer Editor:** Statt die Karte per YAML zu konfigurieren, kann sie
über die normale Lovelace-Karten-Auswahl bearbeitet werden ("Karte
bearbeiten" → es öffnet sich automatisch ein Home-Assistant-Standardformular
statt des YAML-Editors). Dort lassen sich Titel, alle fünf Sensoren sowie
die Zeilenanzahl per Eingabefeld/Entity-Picker setzen und jede der sieben
Spalten (Name, Nummer, eigene Rufnummer, Gerät, Dauer, Datum, VIP) einzeln
per Schalter ein-/ausblenden. Die tatsächlichen Entity-IDs findest du unter
Einstellungen → Geräte & Dienste → Entitäten (Suche nach
"Anrufe"/"Call monitor"/"Anrufbeantworter").

### Variante 2: flex-table-card (YAML, spaltenweise ein-/ausblendbar)

Für eine klassische, tabellarische Darstellung mit frei konfigurierbaren
Spalten: [`examples/dashboard_flex_table.yaml`](examples/dashboard_flex_table.yaml).
Benötigt die separat über HACS installierbare Community-Karte
["flex-table-card"](https://github.com/custom-cards/flex-table-card).

## Icon

Home Assistant unterstützt seit Version 2026.3 eigene Marken-Icons für
Custom Integrations über einen `brand/`-Unterordner (`icon.png`,
`logo.png`, optional `@2x`- und `dark_`-Varianten) - ganz ohne Eintrag in
der offiziellen `home-assistant/brands`-Sammlung. Dieses Repository liefert
ab Version 1.0.1 ein FRITZ!-Icon (`brand/icon.png`, `brand/logo.png`) mit
aus - es wird ohne weitere Konfiguration automatisch in der
Integrationsliste sowie als Geräte-Icon verwendet. Die Quelldatei war ein
kleines JPEG (165×153 px), das auf ein quadratisches 256×256-PNG
aufbereitet wurde; wer eine höher aufgelöste offizielle Vektor-/Bilddatei
hat, kann `brand/icon.png`/`brand/logo.png` jederzeit durch eine bessere
Version ersetzen (z. B. von
[home-assistant.io/integrations/fritzbox_callmonitor](https://www.home-assistant.io/integrations/fritzbox_callmonitor/)).

Die Entitäten selbst haben bereits passende Icons (`mdi:phone`,
`mdi:phone-incoming`, `mdi:phone-outgoing`, `mdi:phone-missed`,
`mdi:voicemail`, siehe `icons.json`).

## Bekannte Einschränkungen

- Die FRITZ!Box/`fritzconnection`-API erlaubt nur EINEN gemeinsamen
  Anzahl-*oder*-Tage-Parameter für den kombinierten Anrufabruf (alle Typen
  gemischt), keinen getrennten Parameter je Anruftyp. Um trotzdem
  unabhängige Grenzwerte je Sensor anzubieten, lädt die Integration je
  Aktualisierungszyklus einmal die letzten 90 Tage (alle Typen kombiniert)
  und wendet die eigene Einstellung jedes Sensors anschließend clientseitig
  an. Praktische Folge: ein auf "Tage" eingestellter Sensor kann nie weiter
  als 90 Tage zurückblicken; ein auf "Anzahl" eingestellter Sensor zeigt
  weniger als den konfigurierten Wert, falls es innerhalb dieser 90 Tage
  schlicht nicht genug Anrufe dieses Typs gab.
- Die feste entity_id (siehe [Entity-IDs](#entity-ids) oben) gilt nur für
  neu angelegte Entities; bei Bestandssystemen bleibt die bisherige
  entity_id erhalten, bis die Entity manuell gelöscht und neu angelegt wird
  - das ist bewusstes Home-Assistant-Verhalten, keine Einschränkung dieser
  Integration.
- **Anrufbeantworter-Sensor und -Wiedergabe sind experimentell und bislang
  nicht an einer echten FRITZ!Box getestet.** Die Integration nutzt dafür
  die TR-064-Aktion `X_AVM-DE_TAM1`/`GetMessageList`; AVMs eigene
  Dokumentation und Drittquellen sind sich uneinig, ob der zurückgegebene
  URL-Parameter `NewURL` oder `NewMessageListURL` heißt - die Integration
  prüft beides. Funktioniert der Sensor auf deiner FRITZ!Box nicht (0
  Nachrichten trotz vorhandener Sprachnachrichten, oder eine Warnung dazu im
  Log), bitte als GitHub-Issue mit dem Log-Auszug melden, damit sich das an
  die tatsächliche FRITZ!OS-Version anpassen lässt. Bewusst **nicht**
  unterstützt: Faxnachrichten.
- Die Anrufbeantworter-Wiedergabe läuft über einen serverseitigen,
  Home-Assistant-authentifizierten Proxy (die FRITZ!Box-Anmeldedaten
  verlassen dabei nie den Home-Assistant-Server); pro Wiedergabe wird die
  Audiodatei einmal komplett von der FRITZ!Box geladen, es gibt aktuell kein
  Streaming/Caching.

## Versionshistorie

- **1.0.1**: Fünf separate Sensoren (`_live`/`_eingehend`/`_ausgehend`/
  `_verpasst`/`_anrufbeantworter`) mit sprachabhängigem Anzeigenamen
  (Deutsch/Englisch) und fest reservierter, sprachneutraler entity_id für
  neu angelegte Entities; je Verlaufs-Sensor unabhängig einstellbare
  Verlaufstiefe (Anzahl-Dropdown mit festen Presets oder Tage), bereits bei
  der Erst-Einrichtung wählbar; mitgelieferte interaktive Dashboard-Karte
  `fritzbox-anrufe-card` (Icon-Filterleiste, Live-Banner, responsives
  Layout, grafischer Karten-Editor mit Sensor-/Zeilen-/Spaltenauswahl);
  **experimenteller** Anrufbeantworter-Sensor mit im Dashboard direkt
  abspielbaren Sprachnachrichten (authentifizierter Server-Proxy, siehe
  [Bekannte Einschränkungen](#bekannte-einschränkungen)); FRITZ!-Marken-Icon
  (`brand/`); Übersetzungsdateien (`translations/`) ergänzt, die für
  Home-Assistant-Custom-Integrations zwingend nötig sind, damit übersetzte
  Entitätsnamen überhaupt greifen.
- **1.0.0**: Umbenennung von `fritzbox_callmonitor` auf `fritzbox_anrufe`;
  drei neue Verlaufs-Sensoren für eingehende/ausgehende/verpasste Anrufe
  (TR-064-basiert) mit gemeinsam konfigurierbarer Verlaufstiefe
  (Anzahl oder Tage); `flex-table-card`-Beispielkarte.

## Fehlerbehebung

- **Verlaufs-Sensoren zeigen `unavailable`**: Kontoberechtigung
  "Sprachnachrichten, Faxnachrichten, FRITZ!App Fon und Anrufliste" prüfen
  (siehe [Voraussetzungen](#voraussetzungen)); Fehlermeldung dazu erscheint
  im Home-Assistant-Log.
- **Integration erscheint nach Update nicht mehr in "Geräte & Dienste"**:
  Meist ein unvollständiger Download/Cache-Rest. Ordner
  `custom_components/fritzbox_anrufe` komplett löschen, in HACS erneut
  herunterladen, Home Assistant vollständig neu starten.
- **Sensoren zeigen nur den Gerätenamen statt "Eingehende Anrufe" etc.**:
  Home Assistant vollständig neu starten (Übersetzungen werden beim Start
  geladen); falls das nicht reicht, die betroffenen Entitäten einmal löschen
  und die Integration neu laden lassen.
- **Dashboard-Karte "fritzbox-anrufe-card" wird nicht gefunden**: Home
  Assistant nach der Installation/dem Update vollständig neu gestartet?
  Andernfalls Browser-Cache leeren (Strg+Shift+R).
- **Anrufbeantworter-Sensor zeigt immer 0 Nachrichten / Warnung im Log zu
  `GetMessageList`**: experimentelle Funktion, siehe
  [Bekannte Einschränkungen](#bekannte-einschränkungen) - bitte mit dem
  Log-Auszug als GitHub-Issue melden.
- **Sprachnachricht lässt sich in der Karte nicht abspielen**: prüfen, ob
  die Kontoberechtigung "Sprachnachrichten, Faxnachrichten, FRITZ!App Fon
  und Anrufliste" gesetzt ist; ansonsten Home-Assistant-Log nach Warnungen
  von `fritzbox_anrufe` zur betroffenen Nachrichten-ID durchsuchen.
