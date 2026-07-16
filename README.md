# fritzbox_anrufe
Eine Home Assistant Integration

## Sensoren

Pro konfiguriertem Telefonbuch/FRITZ!Box-Konto werden vier Sensoren angelegt:

- **Live-Callmonitor** (bestehend, unverändert): Status `ringing`/`dialing`/`talking`/`idle`
  in Echtzeit über den Callmonitor (TCP-Port 1012).
- **Eingehende Anrufe** (`fritzbox_anrufe_eingehend`): Anzahl als Zustand,
  vollständige Liste im Attribut `calls`.
- **Ausgehende Anrufe** (`fritzbox_anrufe_ausgehend`): wie oben, ausgehende Anrufe.
- **Verpasste Anrufe** (`fritzbox_anrufe_verpasst`): wie oben, verpasste Anrufe.

Die drei Verlaufs-Sensoren werden **nicht** über den Callmonitor befüllt, sondern
alle 5 Minuten per TR-064 (`X_AVM-DE_OnTel`, `GetCallList`) von der FRITZ!Box
abgerufen – der Callmonitor liefert nur Live-Ereignisse, keine Historie.

### Voraussetzung: Kontoberechtigung auf der FRITZ!Box

Das für die Integration verwendete FRITZ!Box-Benutzerkonto benötigt unter
`FRITZ!Box-Benutzer → Berechtigungen` das Recht
**"Sprachnachrichten, Faxnachrichten, FRITZ!App Fon und Anrufliste"**, sowie
Zugriff auf die FRITZ!Box-Einstellungen (für TR-064). Fehlt die Berechtigung,
bleiben nur die drei neuen Verlaufs-Sensoren `unavailable` – der Live-Sensor
funktioniert davon unabhängig weiter.

### Verlaufstiefe konfigurieren

Über die Integrations-Optionen (Einstellungen → Geräte & Dienste →
fritzbox_anrufe → Konfigurieren) lässt sich einstellen, ob die drei
Verlaufs-Sensoren nach **Anzahl** (Standard: 20 Anrufe) oder nach
**Tagen** (Standard: 7 Tage) begrenzt werden.

### Entity-IDs

Die Sensoren heißen intern `fritzbox_anrufe_eingehend`/`_ausgehend`/`_verpasst`
(Übersetzungsschlüssel). Die tatsächlich vergebene Entity-ID leitet sich in
Home Assistant automatisch aus Gerätename + Sensorname ab (z. B.
`sensor.fritz_box_7590_eingehende_anrufe`) – Home Assistant bietet keinen
unterstützten Mechanismus, mit dem eine Integration die Entity-ID für
registry-basierte Entities selbst fest vorschreiben kann. Wer exakt
`sensor.fritzbox_anrufe_eingehend` (o. ä.) haben möchte, kann die Entity einmalig
unter Einstellungen → Geräte & Dienste → Entitäten → Zahnrad-Symbol →
"Entitäts-ID" umbenennen; die Umbenennung bleibt dauerhaft erhalten.

## Dashboard-Karte

Siehe [`examples/dashboard_flex_table.yaml`](examples/dashboard_flex_table.yaml)
für eine Beispielkarte, die alle drei Anruflisten in einer Tabelle
zusammenführt (Spalten je nach Bedarf in der YAML-Konfiguration ein-/ausblendbar)
und den aktuellen Live-Anruf oberhalb der Tabelle einblendet, sobald ein
Gespräch läuft. Benötigt die Community-Karte
["flex-table-card"](https://github.com/custom-cards/flex-table-card) (über HACS
installierbar).

Eine eigene Custom Card mit grafischem Spalten-Ein-/Ausblende-Editor (statt
YAML-Konfiguration) ist als nächster Ausbauschritt geplant.
