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
  Zeilenanzahl, einzeln zuschaltbare Kategorien (Alle/Gesamt, Eingehend,
  Ausgehend, Verpasst, Anrufbeantworter) und einzeln zuschaltbare Spalten
  (Name, Nummer, eigene Rufnummer, Gerät, Dauer, Datum, VIP) lassen sich
  ohne YAML einstellen.
- **Experimentell:** Anrufbeantworter-Sensor mit Nachrichtenliste (an echter
  Hardware bestätigt funktionsfähig) und abspielbaren Sprachnachrichten
  direkt im Dashboard (siehe [Bekannte Einschränkungen](#bekannte-einschränkungen)),
  als 5. Symbol/Tab in der Kartenkopfzeile - nicht als Bereich unterhalb der
  Anrufliste.
- Alternative: einfache YAML-Tabellenkarte auf Basis von `flex-table-card`
  (siehe [`examples/dashboard_flex_table.yaml`](examples/dashboard_flex_table.yaml)).

## Voraussetzungen

**Wichtig:** Die folgenden zwei Schritte müssen **direkt in der
FRITZ!Box-Oberfläche** (`http://fritz.box` oder die IP der Box) erledigt
werden, **bevor** die Integration in Home Assistant installiert/eingerichtet
wird - ohne sie schlägt entweder die Einrichtung fehl oder einzelne Sensoren
bleiben dauerhaft `unavailable`.

### 1. Callmonitor aktivieren

Der Live-Anrufmonitor-Sensor (`fritzbox_anrufe_live`) hört auf einem eigenen
Port (1012) mit, der auf der FRITZ!Box standardmäßig **deaktiviert** ist:

1. Ein an der FRITZ!Box angeschlossenes Telefon (Fest- oder IP-Telefon)
   nehmen und die Ziffernfolge `#96*5*` wählen. Kurz klingeln lassen bzw.
   auflegen reicht - der Anruf muss nicht angenommen werden.
2. Zum Deaktivieren (z. B. zum Testen) analog `#96*4*` wählen.

Zusätzlich muss der **TR-064-Zugriff** aktiviert sein - darüber laufen die
Anruflisten-, Anrufbeantworter- und Options-Abfragen:

3. FRITZ!Box-Oberfläche → **Heimnetz → Netzwerk → Netzwerkeinstellungen**
   (Reiter) → Häkchen bei **"Zugriff für Anwendungen zulassen"** setzen und
   speichern.

Ohne Schritt 1 bleibt ausschließlich der Live-Sensor `unavailable` (der Rest
funktioniert unabhängig davon); ohne Schritt 3 funktioniert die gesamte
Integration nicht, da sie ohne TR-064 keine Verbindung aufbauen kann.

### 2. FRITZ!Box-Benutzerkonto einrichten

Die Integration meldet sich mit einem regulären FRITZ!Box-Benutzerkonto an
(nicht mit einem separaten API-Schlüssel) - dieses Konto muss vorher
angelegt bzw. mit den richtigen Berechtigungen versehen werden:

1. FRITZ!Box-Oberfläche → **System → FRITZ!Box-Benutzer** →
   "Benutzer hinzufügen" (oder ein bestehendes Konto bearbeiten).
2. Benutzername und Kennwort vergeben - diese Zugangsdaten werden später bei
   der Einrichtung der Integration in Home Assistant abgefragt.
3. Unter **"Berechtigungen für diesen Benutzer"** mindestens ankreuzen:
   - **"FRITZ!Box-Einstellungen"** (Grundvoraussetzung für jeglichen
     TR-064-Zugriff).
   - **"Sprachnachrichten, Faxnachrichten, FRITZ!App Fon und Anrufliste"**
     (wird für die drei Verlaufs-Sensoren UND den
     Anrufbeantworter-Sensor benötigt). Fehlt diese Berechtigung, bleiben
     genau diese vier Sensoren `unavailable` - der Live-Sensor ist davon
     unabhängig, da er nicht über TR-064, sondern über den separaten
     Callmonitor-Port läuft.
4. Speichern.

Erst wenn beide Schritte erledigt sind, mit [Installation](#installation)
fortfahren.

### Home Assistant

Aktuelle Version empfohlen (getestet mit Python 3.14+, wie von aktuellen
Home-Assistant-Releases vorausgesetzt).

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
nachdem die Integration installiert/aktualisiert wurde). Es gibt bewusst nur
diesen einen Kartentyp - Anrufliste und Anrufbeantworter teilen sich eine
Karte, jede Kategorie darin lässt sich aber einzeln ein-/ausblenden (siehe
unten).

Funktionen:

- Icon-Leiste oben zum Filtern per Klick - fünf mögliche Symbole: Alle/
  Gesamt, Eingehend, Ausgehend, Verpasst und (als 5. Symbol)
  **Anrufbeantworter**. Welche davon überhaupt erscheinen, ist einzeln
  konfigurierbar (siehe **Kategorien** unten). Ist nach dem Ausblenden nur
  noch eine Kategorie übrig, entfällt die Leiste ganz.
- Kategorie "Alle"/"Gesamt" zeigt die neuesten Anrufe aller aktivierten
  Anruftypen gemischt (sortiert nach Datum), begrenzt auf `max_rows` Zeilen
  (Standard: 10). Anrufbeantworter-Nachrichten zählen NICHT zu "Alle" - sie
  erscheinen ausschließlich im eigenen Anrufbeantworter-Tab.
- Findet gerade ein Gespräch statt (Live-Sensor ≠ "idle"), erscheint
  oberhalb der Icon-Leiste automatisch ein hervorgehobenes Live-Banner.
- **Experimentell:** Klick auf das Anrufbeantworter-Symbol (nur sichtbar,
  wenn ein Anrufbeantworter-Sensor eingetragen ist) wechselt den
  Karteninhalt komplett zur Nachrichtenliste
  (Name/Nummer/Zeitpunkt/Dauer, neue Nachrichten farblich markiert) samt
  "Abspielen"-Button pro Nachricht - genau wie bei den Anruf-Tabs ersetzt
  das die Anrufliste, es erscheint kein zusätzlicher Bereich darunter.
  Siehe [Wiedergabe der Anrufbeantworter-Nachrichten](#wiedergabe-der-anrufbeantworter-nachrichten)
  unten für Details, wie das Abspielen technisch funktioniert.
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
show_alle: true
show_eingehend: true
show_ausgehend: true
show_verpasst: true
show_anrufbeantworter: true
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
statt des YAML-Editors). Dort lassen sich Titel, alle fünf Sensoren sowie die
Zeilenanzahl per Eingabefeld/Entity-Picker setzen. Die tatsächlichen
Entity-IDs findest du unter Einstellungen → Geräte & Dienste → Entitäten
(Suche nach "Anrufe"/"Call monitor"/"Anrufbeantworter").

**Kategorien:** Fünf Schalter (`show_alle`, `show_eingehend`,
`show_ausgehend`, `show_verpasst`, `show_anrufbeantworter`) blenden ganze
Kategorien/Tabs ein oder aus. Bei den vier Anruf-Kategorien reicht dafür der
Schalter allein; der Anrufbeantworter-Tab braucht zusätzlich einen
konfigurierten `entity_voicemail` - ohne Sensor bleibt er auch bei
`show_anrufbeantworter: true` ausgeblendet, da es nichts anzuzeigen gäbe.
Eine deaktivierte Anruf-Kategorie verschwindet aus der Icon-Leiste und wird
auch aus der "Alle"/"Gesamt"-Sammelansicht herausgerechnet.

**Spalten:** Sieben weitere Schalter (`show_name`, `show_number`,
`show_own_number`, `show_device`, `show_duration`, `show_date`, `show_vip`)
blenden einzelne Spalten der Anrufliste ein oder aus.

### Wiedergabe der Anrufbeantworter-Nachrichten

Ein `<audio src="...">` kann in Home Assistant grundsätzlich keine
Zugangsdaten mitschicken - der Browser hängt an eine reine Medien-URL keinen
Authorization-Header an. Deshalb setzt die Karte die Aufnahme-URL nicht
direkt als `src`, sondern zeigt pro Nachricht zunächst einen
"Abspielen"-Button. Erst ein Klick darauf lädt die Aufnahme über die
authentifizierte Fetch-Funktion, die Home Assistant Karten dafür zur
Verfügung stellt (`hass.fetchWithAuth`), und übergibt sie danach als
abspielbaren Audio-Player. Ohne diesen Umweg schlägt die Wiedergabe fehl und
im Home-Assistant-Log erscheint eine Meldung wie *"Login attempt or request
with invalid authentication ... /api/fritzbox_anrufe/tam_media/..."* vom
`http.ban`-Modul - das war das Verhalten vor diesem Fix.

### Variante 2: flex-table-card (YAML, spaltenweise ein-/ausblendbar)

Für eine klassische, tabellarische Darstellung mit frei konfigurierbaren
Spalten: [`examples/dashboard_flex_table.yaml`](examples/dashboard_flex_table.yaml).
Benötigt die separat über HACS installierbare Community-Karte
["flex-table-card"](https://github.com/custom-cards/flex-table-card).

## Icon

Home Assistant unterstützt seit Version 2026.3 eigene Marken-Icons für
Custom Integrations über einen `brand/`-Unterordner (`icon.png`,
`logo.png`, optional `@2x`- und `dark_`-Varianten) - ganz ohne Eintrag in
der offiziellen `home-assistant/brands`-Sammlung (die für Custom
Integrations inzwischen keine Icons mehr annimmt). Dieses Repository
liefert ab Version 1.0.1 ein FRITZ!-Icon (`brand/icon.png`,
`brand/logo.png`) mit aus - es wird ohne weitere Konfiguration automatisch
in der Integrationsliste sowie als Geräte-Icon verwendet. Die Quelldatei
war ein kleines JPEG (165×153 px), das auf ein quadratisches 256×256-PNG
aufbereitet wurde; wer eine höher aufgelöste offizielle Vektor-/Bilddatei
hat, kann `brand/icon.png`/`brand/logo.png` jederzeit durch eine bessere
Version ersetzen (z. B. von
[home-assistant.io/integrations/fritzbox_callmonitor](https://www.home-assistant.io/integrations/fritzbox_callmonitor/)).

Die Entitäten selbst haben bereits passende Icons (`mdi:phone`,
`mdi:phone-incoming`, `mdi:phone-outgoing`, `mdi:phone-missed`,
`mdi:voicemail`, siehe `icons.json`).

**Icon erscheint nicht auf der HACS-Downloads-Seite:** Das ist ein
bekannter, aktuell offener Fehler in HACS selbst, nicht in dieser
Integration. HACS' eigene Downloads-Übersicht lädt Icons weiterhin über
die alte öffentliche CDN (`data-v2.hacs.xyz`/`brands.home-assistant.io`),
kennt den seit Home Assistant 2026.3 unterstützten Weg für inline
mitgelieferte Icons (`brand/`-Ordner, wie oben beschrieben) aber noch nicht
- siehe [hacs/integration#5223](https://github.com/hacs/integration/issues/5223)
und [hacs/integration#5171](https://github.com/hacs/integration/issues/5171).
Für Custom Integrations akzeptiert `home-assistant/brands` inzwischen
bewusst keine Icons mehr, ein Workaround auf Integrationsseite existiert
also nicht. Wichtig: Das Icon wird davon unabhängig überall sonst in Home
Assistant korrekt angezeigt (Einstellungen → Geräte & Dienste, Geräteseite
usw.) - betroffen ist ausschließlich die HACS-eigene Downloads-Liste, bis
die dortigen Maintainer den Fehler beheben.

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
- **Anrufbeantworter-Sensor und -Wiedergabe sind experimentell**, aber
  inzwischen an echter Hardware bestätigt funktionsfähig (u. a. unter
  FRITZ!OS 8.24) - sowohl die Nachrichtenliste (Sensor
  `fritzbox_anrufe_anrufbeantworter`, TR-064-Aktion
  `X_AVM-DE_TAM1`/`GetMessageList`) als auch die Wiedergabe. Der
  Audio-Download läuft über
  `/cgi-bin/luacgi_notimeout?sid=...&script=/lua/photo.lua&myabfile=...`
  gegen den normalen Web-UI-Port (80/443) der FRITZ!Box - **nicht** über
  `download.lua`, wie es die in der Nachrichtenliste enthaltene `Path`-
  Angabe nahelegt, und **nicht** über den TR-064-Port (i. d. R. 49000).
  Da unterschiedliche FRITZ!OS-Versionen sich in Testberichten uneinig
  waren, woher die dafür nötige Sitzung (`sid`) stammen muss, probiert die
  Integration bei Bedarf automatisch zwei Varianten durch: zuerst die in
  der `GetMessageList`-Antwort enthaltene sid (ohne zusätzliche Anmeldung),
  bei Fehlschlag eine vollständige FRITZ!Box-Weboberflächen-Anmeldung als
  Rückfalloption. Falls die Wiedergabe auf einer bestimmten FRITZ!OS-
  Version dennoch fehlschlägt, bitte mit dem vollständigen Log-Auszug
  (`custom_components.fritzbox_anrufe.*`, insbesondere dem/den
  HTTP-Statuscode(s)) als GitHub-Issue melden. Bewusst **nicht**
  unterstützt: Faxnachrichten.
- Die Anrufbeantworter-Wiedergabe läuft über einen serverseitigen,
  Home-Assistant-authentifizierten Proxy (die FRITZ!Box-Anmeldedaten
  verlassen dabei nie den Home-Assistant-Server); pro Wiedergabe wird die
  Audiodatei einmal komplett von der FRITZ!Box geladen, es gibt aktuell kein
  Streaming/Caching. Aus demselben Grund ist bewusst ein "Abspielen"-Button
  statt eines direkt befüllten `<audio src="...">` verbaut - siehe
  [Wiedergabe der Anrufbeantworter-Nachrichten](#wiedergabe-der-anrufbeantworter-nachrichten).

## Versionshistorie

- **1.0.2**: Fix für "Dashboard-Karte wird nicht gefunden" bzw.
  "Konfigurationsfehler: Custom-Element ist im Frontend unbekannt" trotz
  fehlerfrei geladener Integration und vorhandener Kartendatei - betraf
  einen Teil der Installationen. Ursache (durch Tests eines Nutzers,
  marcedale, an echter Hardware bestätigt): die Karte wurde auf zwei
  Wegen gleichzeitig registriert, direkt eingebettet über
  `add_extra_js_url()` **und** als Ressourcen-Eintrag unter
  Einstellungen → Dashboards → Ressourcen. Ein Browser führt eine
  Modul-URL aber nur genau einmal aus - schlug der eingebettete Weg fehl
  (z. B. wegen einer bereits zwischengespeicherten Startseite in Browser
  oder Companion-App), galt die URL als "abgearbeitet", und der
  Ressourcen-Eintrag konnte sie danach nicht mehr laden, selbst wenn er
  korrekt angelegt war. Fix: Die Karte wird jetzt ausschließlich noch als
  Ressourcen-Eintrag geladen (`add_extra_js_url()` entfernt), inklusive
  Versionsparameter an der URL (`?v=<Version>`) zur zuverlässigen
  Cache-Invalidierung nach Updates. Details siehe
  [Fehlerbehebung](#fehlerbehebung). Zusätzlich robuster gegen eine falsch
  konfigurierte `entity_live`: Das Live-Banner erscheint jetzt nur noch bei
  den drei bekannten Anruf-Zuständen (Klingelt/Wählen/Gespräch läuft) statt
  bei "allem außer ein paar bekannten Ruhezuständen" - zeigt ein falsch
  zugeordneter Sensor (z. B. der Anrufbeantworter-Sensor mit seiner
  Nachrichtenanzahl als Zustand) also z. B. den Wert `10`, bleibt das
  Banner jetzt korrekt ausgeblendet statt die Zahl dauerhaft anzuzeigen.
- **1.0.1**: Fünf separate Sensoren (`_live`/`_eingehend`/`_ausgehend`/
  `_verpasst`/`_anrufbeantworter`) mit sprachabhängigem Anzeigenamen
  (Deutsch/Englisch) und fest reservierter, sprachneutraler entity_id für
  neu angelegte Entities; je Verlaufs-Sensor unabhängig einstellbare
  Verlaufstiefe (Anzahl-Dropdown mit festen Presets oder Tage), bereits bei
  der Erst-Einrichtung wählbar; mitgelieferte interaktive Dashboard-Karte
  `fritzbox-anrufe-card` (Icon-Filterleiste, Live-Banner, responsives
  Layout, grafischer Karten-Editor mit Sensor-/Zeilen-/Spaltenauswahl,
  Zeilenanzahl per Schieberegler 1-15) mit **experimentellem**
  Anrufbeantworter-Sensor (Nachrichtenliste und Wiedergabe an echter
  Hardware bestätigt funktionsfähig, u. a. unter FRITZ!OS 8.24) samt im
  Dashboard direkt abspielbaren Sprachnachrichten über einen
  authentifizierten Server-Proxy und "Abspielen"-Button
  (`hass.fetchWithAuth`; Download-Details siehe
  [Bekannte Einschränkungen](#bekannte-einschränkungen)); alle Kategorien
  (Alle/Gesamt, Eingehend, Ausgehend, Verpasst, Anrufbeantworter) einzeln
  ein-/ausblendbar auf derselben Karte; FRITZ!-Marken-Icon (`brand/`);
  Übersetzungsdateien (`translations/`) ergänzt, die für
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
- **Dashboard-Karte "fritzbox-anrufe-card" wird nicht gefunden /
  "Konfigurationsfehler: Custom-Element ist im Frontend unbekannt"**,
  obwohl die Integration fehlerfrei lädt und die Datei
  `custom_components/fritzbox_anrufe/www/fritzbox-anrufe-card.js`
  nachweislich vorhanden ist: Seit Version 1.0.2 (endgültig ab 1.0.2b1)
  wird die Karte ausschließlich noch als echter, dauerhafter
  Ressourcen-Eintrag unter Einstellungen → Dashboards → Ressourcen
  registriert - das ist inzwischen der einzige Ladeweg. (Frühere
  1.0.2-Vorabversionen registrierten die Karte zusätzlich über
  `add_extra_js_url()` direkt in der Startseite; das führte auf manchen
  Installationen dazu, dass die Karte nach einem Neustart der Companion-App
  dauerhaft verschwand, weil ein Browser eine Modul-URL nur einmal ausführt
  - schlug der eingebettete Weg fehl, blieb auch der Ressourcen-Eintrag
  wirkungslos. Seit 1.0.2b1 gibt es nur noch den einen, zuverlässigen Weg.)
  Prüfen: erscheint unter Einstellungen → Dashboards → Ressourcen ein
  Eintrag für `/fritzbox_anrufe_files/fritzbox-anrufe-card.js` (mit einem
  `?v=...`-Versionsparameter)? Fehlt er, läuft das Dashboard vermutlich im
  YAML-Modus - dort verwaltet Home Assistant Ressourcen ausschließlich über
  `configuration.yaml`, ein automatischer Eintrag ist dann technisch nicht
  möglich; die Zeile muss einmalig manuell in die `lovelace:`-Konfiguration
  eingetragen werden (`resources: - url:
  /fritzbox_anrufe_files/fritzbox-anrufe-card.js`, `type: module` - ohne
  Versionsparameter, da hier keine automatische Aktualisierung stattfindet).
  Ist der Eintrag vorhanden, aber die Karte lädt trotzdem nicht: einmal den
  Service Worker der Website löschen (Browser-DevTools → Anwendung/
  Application → Service Worker → "Unregister") bzw. bei der Companion-App
  den App-Cache leeren, danach normal neu laden.
- **Anrufbeantworter-Sensor zeigt immer 0 Nachrichten / Warnung im Log zu
  `GetMessageList`**: experimentelle Funktion, siehe
  [Bekannte Einschränkungen](#bekannte-einschränkungen) - bitte mit dem
  Log-Auszug als GitHub-Issue melden.
- **Log-Meldung "Login attempt or request with invalid authentication ...
  /api/fritzbox_anrufe/tam_media/..." (Quelle `components/http/ban.py`)**:
  war vor der ersten Anrufbeantworter-Korrektur das erwartete Verhalten,
  wenn eine Sprachnachricht abgespielt wurde - behoben, siehe
  [Wiedergabe der Anrufbeantworter-Nachrichten](#wiedergabe-der-anrufbeantworter-nachrichten).
  Tritt es weiterhin auf: Integration auf die neueste Version aktualisiert
  und Home Assistant vollständig neu gestartet (nicht nur neu geladen), damit
  die aktualisierte Karten-Datei vom Browser geladen wird? Zusätzlich
  Browser-Cache leeren (Strg+Shift+R).
- **Sprachnachricht lässt sich in der Karte nicht abspielen** (Button zeigt
  "Fehler – erneut versuchen"): prüfen, ob die Kontoberechtigung
  "Sprachnachrichten, Faxnachrichten, FRITZ!App Fon und Anrufliste" gesetzt
  ist; ansonsten Home-Assistant-Log nach Warnungen von `fritzbox_anrufe` zur
  betroffenen Nachrichten-ID durchsuchen, sowie die Browser-Konsole (F12) auf
  Fehler beim Laden von `/api/fritzbox_anrufe/tam_media/...` prüfen.
- **Log-Meldung `custom_components.fritzbox_anrufe.http`: "Fehler beim
  Abrufen der Anrufbeantworter-Nachricht ...: Anrufbeantworter-Download
  fehlgeschlagen (HTTP 404) nach N Versuch(en) mit unterschiedlichen
  Sitzungen"**: Die Anrufbeantworter-Wiedergabe funktioniert an echter
  Hardware bestätigt (u. a. FRITZ!OS 8.24) - tritt der Fehler dennoch auf,
  zunächst prüfen, ob wirklich die neueste Version installiert ist
  (Einstellungen → Geräte & Dienste → FRITZ!Box Anrufe → Version; nach dem
  Ersetzen der Dateien Home Assistant **vollständig neu starten**, nicht
  nur neu laden). Die Integration probiert bereits automatisch mehrere
  `sid`-Quellen gegen den Web-UI-Port durch (siehe
  [Bekannte Einschränkungen](#bekannte-einschränkungen)) und meldet erst
  einen Fehler, wenn alle davon fehlschlagen - "N Versuch(en)" in der
  Meldung zeigt, wie viele das waren. Tritt der Fehler auf der aktuellen
  Version weiterhin auf, bitte mit dem vollständigen Log-Auszug **und dem
  darin enthaltenen HTTP-Statuscode sowie der FRITZ!OS-Version** als
  GitHub-Issue melden (kann z. B. auch an ein durch die FRITZ!Box-
  Blockzeit nach mehreren Fehlversuchen gesperrtes Konto liegen - in dem
  Fall kurz warten und erneut versuchen).
- **Grafischer Karten-Editor: "Max. Zeilen" lässt sich nicht auf einen
  neuen Wert ändern / springt zurück**: dafür ist ein Schieberegler statt
  eines Texteingabefelds verbaut - Home Assistant nach dem Update
  vollständig neu starten und Browser-Cache leeren (Strg+Shift+R). Bis auf
  15 Zeilen per Schieberegler einstellbar; höhere Werte weiterhin über den
  YAML-Editor der Karte möglich.
