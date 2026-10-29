# Changelog

## 0.1.3 (2026-10-29)

- IPP: HTTP 503 wird bis zu zweimal wiederholt (Brother QL antwortet so bei mehreren Abfragen kurz hintereinander).
- Vorschau-Dateinamen eindeutig (Millisekunden + Zähler); vorher überschrieben sich Vorschauen derselben Sekunde.

## 0.1.2 (2026-10-29)

- `quer`: Text quer zur Rolle für kurze Etiketten (z. B. 25 × 38 mm auf 38-mm-Endlos), passend für schmale Klebeflächen ohne Nachschneiden. Nur auf Endlosrollen.

## 0.1.1 (2026-10-29)

- Größenstufe `groesse` für Etiketten (`klein`/`mittel`/`gross`, Standard `mittel`). Vorher füllte die Schrift immer die Rollenbreite, zwei kurze Zeilen mit QR ergaben auf 38 mm endlos ein 155-mm-Etikett (jetzt 70 mm).
- QR-Code skaliert mit dem Textblock, mindestens 15 mm.
- Vorschau quer und lesbar, Druckdatei getrennt (hochkant).
- Klartext-Fehler, wenn der Drucker nicht erreichbar ist.

## 0.1.0 (2026-10-29)

- Etiketten passend zur eingelegten Rolle: Rolle per IPP lesen (Bonjour-Queue wird selbst aufgelöst), Layout für Endlos- und vorgestanzte Rollen, Schrift automatisch, QR-Code, Rahmen, `{datum}`.
- Vorschau ohne Druck; Abbruch, wenn der Auftrag nicht zur Rolle passt.
- Dokumente: PDF direkt, Markdown/HTML per Chrome headless als A4-PDF; Farbe/SW, Duplex, Seitenbereich, Kopien.
- Druckaufträge anzeigen und abbrechen.
