# Open Electribe Editor

Ein plattformunabhängiger Desktop-Editor für **Korg Electribe `.esx`-Dateien**. Damit lassen sich Patterns, Samples, Songs und globale Parameter einer Electribe außerhalb des Geräts bearbeiten, verwalten und austauschen.

## Funktionen

- **Info-Tab** – Übersicht über Dateistatistiken (genutzte Patterns/Samples/Songs, belegter Sample-Speicher)
- **Global-Tab** – Bearbeiten der globalen Parameter der `.esx`-Datei
- **Patterns-Tab** – Patterns anzeigen und bearbeiten, inkl. Export/Import einzelner Patterns als `.esxpat` (samt referenzierter Samples), um sie zwischen Projekten auszutauschen
- **Samples-Tab** – Samples importieren (WAV, optional automatische Mono-Konvertierung), Wellenform-Anzeige, Vorhören per eingebautem Audio-Player, einzelne oder ungenutzte Samples löschen
- **Songs-Tab** – Songs anzeigen und bearbeiten
- **Datei-Explorer** – Andockbare Seitenleiste zum Navigieren im Dateisystem und Öffnen von `.esx`/`.wav`/`.mp3`/`.aiff`-Dateien
- **Pattern-Browser** – Verwaltung exportierter Patterns
- Dunkles UI-Theme

## Voraussetzungen

- Python 3.11 oder neuer
- Windows oder macOS (getestet; sollte auch unter Linux mit PyQt6/PortAudio laufen)

## Installation

### Option A: Fertiges Windows-Build verwenden

1. Gehe im Repository auf den Reiter **Releases** und lade die neueste `OpenElectribeEditor.exe` herunter (bei getaggten Versionen), **oder**
2. gehe auf den Reiter **Actions** → wähle den neuesten erfolgreichen *Build Windows EXE*-Lauf → lade das Artifact `OpenElectribeEditor-windows-exe` herunter (erfordert einen GitHub-Login).
3. Entpacke das Artifact/die Datei und starte `OpenElectribeEditor.exe` direkt – es ist keine Python-Installation nötig.

> Diese Build-Variante gibt es aktuell nur für Windows. Für macOS bitte die manuelle Installation aus dem Quellcode nutzen (siehe unten).

### Option B: Manuelle Installation aus dem Quellcode

#### Windows

```powershell
# Repository klonen
git clone https://github.com/<user>/open-electribe-editor-python.git
cd open-electribe-editor-python

# Virtuelle Umgebung anlegen und aktivieren
python -m venv venv
venv\Scripts\activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Anwendung starten
python main.py
```

#### macOS

```bash
# Repository klonen
git clone [https://github.com/<user>/open-electribe-editor-python.git](https://github.com/vxdy/Open-Korg-ESX-Sample-Manager)
cd open-electribe-editor-python

# Virtuelle Umgebung anlegen und aktivieren
python3 -m venv venv
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt

# Anwendung starten
python3 main.py
```

**Hinweis (macOS):** `sounddevice` benötigt PortAudio. Bringt die installierte Version kein passendes vorkompiliertes Wheel mit, kann PortAudio via Homebrew nachinstalliert werden:

```bash
brew install portaudio
```


```bash
git tag v1.0.0
git push origin v1.0.0
```

Die Pipeline lässt sich außerdem manuell über *Actions → Build Windows EXE → Run workflow* auslösen.

## Projektstruktur

```
esx/      Parser/Datenmodell für .esx-Dateien (Global Parameters, Patterns, Samples, Songs)
audio/    Sample-Wiedergabe (AudioPlayer)
wav/      WAV/RIFF-Handling für den Sample-Import
ui/       PyQt6-Oberfläche (Hauptfenster, Tabs, Datei-Explorer, Pattern-Browser, Theme)
main.py   Einstiegspunkt der Anwendung
```

## Debug-Daten senden

Unter *Help → Sende Debug Daten* kann optional die Übermittlung von Debug-/Fehlerberichten an einen Debug-Server aktiviert/deaktiviert werden, um bei der Fehlersuche während der Entwicklung zu helfen.
