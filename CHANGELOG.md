# Changelog

## 1.2.0 - 2026-07-14

Ein besonderer Dank gilt AspirinJunkie für seine detaillierten False-Positive-Meldungen und Testfälle, die diese Version erst möglich gemacht haben.

### Fixed

- AutoIt-Quelldateien werden zentral und verlustfrei anhand ihrer BOM- bzw. ANSI-Kodierung gelesen. Unterstützt werden Windows-1252 ohne BOM, UTF-8 mit BOM sowie UTF-16 LE/BE mit BOM; fehlerhafte oder nicht unterstützte Quellen liefern nun einen `Source Read Error` und einen Non-Zero-Exit statt einer falschen `0 errors, 0 warnings`-Freigabe.
- Bedingte Top-Level-Deklarationen nach `If Not IsDeclared(...) Then Global` und einzeilige lokale Deklarationen nach `Then Local` werden erkannt.
- Variablenzugriffe in `ElseIf`-, `Case`-, `Case ... To`- und `Until`-Ausdrücken zählen nun korrekt als Lesezugriffe.
- `StringRegExp` wird abhängig vom dritten Argument als boolesches oder Array-Ergebnis modelliert; die offiziellen symbolischen Array-Flags werden berücksichtigt.
- `Dim` auf bereits vorhandenen lokalen, globalen oder Parameterbindungen wird von einer neuen impliziten Deklaration unterschieden.
- Schreibzugriffe auf beschreibbare `ByRef`-Parameter gelten nicht mehr als Dead Store, da der Wert für den Aufrufer sichtbar ist.
- Duplicate-Declaration-Prüfungen berücksichtigen garantiert terminierende `Return`-/`Exit`-Pfade und melden das sichere, bedingte `Local $iErr`-Muster aus `JSON.au3` nicht mehr.
- Duplicate-Case-Prüfungen unterscheiden redundante Werte derselben `Case`-Klausel von konkurrierenden späteren Case-Zweigen und arbeiten nun in Funktionen und im Top-Level-Scope konsistent.

### Tests

- Regressionstests für alle von AspirinJunkie/Sylvan86 bereitgestellten Fälle A–J sowie nahe Gegenbeispiele ergänzt.
- Binäre Encoding-Tests für Windows-1252, UTF-8-BOM, UTF-16 LE/BE, fehlerhaftes UTF-16 und gemischt kodierte Include-Bäume ergänzt.
- Pfadsensitive Clean-/Counter-Fixtures für bedingte Wiederdeklarationen sowie Scope-Paritätstests für Duplicate Case ergänzt.
- Vollständiger System-Include-Burn-in gegen die bestehende Baseline von 88 Diagnosen verifiziert; Workspace- und externe Include-Diagnosen bleiben bei 0.

### Performance

- Reproduzierbare Laufzeit- und Profiling-Analyse für den kleinen A–J-Korpus und den vollständigen System-Include-Burn-in dokumentiert. Optimierungen bleiben von den semantischen Korrekturen getrennt und werden nur anhand bestätigter Hotspots priorisiert.
- Wiederholte, reine Lexer-Operationen (`split_code_comment`, `strip_strings` und Top-Level-Ausdruckstrennung) sowie Funktionssignatur- und Schlüsselworterkennung werden pro Prozess in begrenzten Caches wiederverwendet; die historische Listen-Schnittstelle der Ausdruckstrennung bleibt dabei erhalten.
- Häufige Block-, Funktions-, Alias- und Return-Prüfungen verwenden billige Schlüsselwort-Guards, bevor reguläre Ausdrücke ausgeführt werden. Der zusätzliche Legacy-Syntaxpass für JSON-Ausgabe bleibt aus Kompatibilitätsgründen erhalten, teilt aber nun bereits berechnete Lexer-Ergebnisse.
- Identische Vorher-/Nachher-Matrix mit je fünf isolierten Prozessen pro Workload: Gesamtzeit für 20 Läufe von 158.541,568 ms auf 144.378,893 ms reduziert (-14.162,675 ms / 8,93 %). Die Mediane verbessern sich für A–J um 7,97 %, Standard-JSON um 11,60 %, Experimental-JSON um 12,12 % und den normalen Experimental-Report um 4,33 %.
- Alle 20 Benchmark-Artefaktpaare liefern identischen präprozessierten Quelltext und nach Entfernung dynamischer Metadaten identische Diagnosereports.

## 1.1.0 - 2026-07-07

- Erste öffentliche Release.
