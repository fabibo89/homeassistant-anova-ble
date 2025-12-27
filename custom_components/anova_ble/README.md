# Anova Precision Cooker BLE Integration für Home Assistant

Diese Integration ermöglicht die Steuerung von Anova Precision Cooker Modellen A2/A3 über Bluetooth Low Energy (BLE) in Home Assistant.

## Features

### Lesbare Werte (Sensoren)
- **Wassertemperatur**: Aktuelle Temperatur des Wassers
- **Zieltemperatur**: Eingestellte Zieltemperatur
- **Timer**: Verbleibende Zeit in Minuten
- **Status**: Ob der Cooker läuft oder gestoppt ist
- **Einheiten**: Temperatur-Einheiten (Celsius/Fahrenheit)

### Schreibbare Werte (Steuerung)
- **Zieltemperatur**: Einstellen der Zieltemperatur (0-100°C)
- **Timer**: Einstellen des Timers in Minuten (0-999)
- **Start/Stop**: Schalter zum Starten und Stoppen des Cookers

## Installation

### Manuelle Installation

1. Kopieren Sie diesen Ordner in das `custom_components` Verzeichnis Ihrer Home Assistant Installation:
   ```
   <config>/custom_components/anova_ble/
   ```

2. Starten Sie Home Assistant neu.

3. Gehen Sie zu **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen**

4. Suchen Sie nach **"Anova Precision Cooker (BLE)"** und folgen Sie den Anweisungen.

5. Wählen Sie Ihr Anova-Gerät aus der Liste der gefundenen Geräte aus.

## Voraussetzungen

- Home Assistant mit aktivierter Bluetooth-Unterstützung
- Anova Precision Cooker Modell A2 oder A3
- Das Gerät muss eingeschaltet und in Bluetooth-Reichweite sein

## Verwendung

Nach der Installation werden automatisch folgende Entities erstellt:

### Sensoren
- `sensor.anova_water_temperature` - Aktuelle Wassertemperatur
- `sensor.anova_target_temperature` - Zieltemperatur
- `sensor.anova_timer` - Verbleibende Zeit
- `sensor.anova_running` - Status (on/off)
- `sensor.anova_units` - Temperatur-Einheiten

### Number Entities
- `number.anova_target_temperature` - Zieltemperatur einstellen
- `number.anova_timer` - Timer einstellen

### Switch Entity
- `switch.anova_running` - Cooker starten/stoppen

## Beispiel-Automatisierung

```yaml
automation:
  - alias: "Anova Sous Vide Start"
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.anova_target_temperature
        data:
          value: 60
      - service: number.set_value
        target:
          entity_id: number.anova_timer
        data:
          value: 120
      - service: switch.turn_on
        target:
          entity_id: switch.anova_running
```

## Technische Details

### BLE Protokoll
Die Integration verwendet das textbasierte BLE-Protokoll der A2/A3 Modelle:
- Service UUID: `0000ffe0-0000-1000-8000-00805f9b34fb`
- Characteristic UUID: `0000ffe1-0000-1000-8000-00805f9b34fb`

### Befehle
- `status` - Status abfragen
- `set temp <wert>` - Temperatur setzen
- `set timer <minuten>` - Timer setzen
- `start` - Cooker starten
- `stop` - Cooker stoppen
- `set units C` - Celsius einstellen
- `set units F` - Fahrenheit einstellen

## Fehlerbehebung

### Gerät wird nicht gefunden
- Stellen Sie sicher, dass das Gerät eingeschaltet ist
- Überprüfen Sie, dass Bluetooth auf Ihrem Home Assistant System aktiviert ist
- Versuchen Sie, das Gerät näher an den Home Assistant Server zu bringen
- Starten Sie Home Assistant neu

### Verbindungsfehler
- Überprüfen Sie, dass das Gerät nicht bereits mit einer anderen App verbunden ist
- Trennen Sie alle anderen Verbindungen zum Gerät
- Versuchen Sie, die Integration zu entfernen und erneut hinzuzufügen

### Keine Daten
- Überprüfen Sie die Logs in Home Assistant auf Fehlermeldungen
- Stellen Sie sicher, dass das Gerät in Reichweite ist
- Versuchen Sie, den Cooker manuell zu starten/stoppen, um die Verbindung zu testen

## Logs

Aktivieren Sie Debug-Logging für detaillierte Informationen:

```yaml
logger:
  default: info
  logs:
    custom_components.anova_ble: debug
```

## Bekannte Einschränkungen

- Die Integration unterstützt derzeit nur A2/A3 Modelle
- Wi-Fi-fähige Modelle werden nicht unterstützt (verwenden Sie die offizielle Anova-Integration)
- Die Temperatur wird immer in Celsius angezeigt, unabhängig von den Geräteeinstellungen

## Entwicklung

Diese Integration basiert auf der [Anova Developer Documentation](https://developer.anovaculinary.com/docs/intro).

## Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert.

## Support

Bei Problemen oder Fragen erstellen Sie bitte ein Issue im Repository oder kontaktieren Sie den Entwickler.

