/*
 * ======================================================================================
 * FACTORY EDGE MONITORING: TWO-STAGE RECIPROCATING AIR COMPRESSOR TELEMETRY
 * ======================================================================================
 * Target Asset: Two-Stage Industrial Reciprocating Air Compressor (15 kW, 10 Bar)
 * Microcontroller: ESP32 DevKit V1 (Wokwi / Hardware Compatible)
 * Protocol: MQTT over TCP (JSON Payload matching Section 11 Standard Contract)
 * 
 * Monitored 5 Physical Sensor Channels:
 *   1. Temperature: Process / Intercooler Temperature (°C)
 *   2. Vibration: Crankcase / Motor Bearing Vibration (g RMS)
 *   3. Pressure: Stage 2 Discharge / Receiver Pressure (bar)
 *   4. Current: Electric Drive Motor Current (A)
 *   5. Speed: Compressor Shaft Rotational Speed (RPM)
 * ======================================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// --------------------------------------------------
// Pin Configuration
// --------------------------------------------------
#define DHTPIN 15            // DHT22 Process/Ambient Temperature Sensor
#define DHTTYPE DHT22

#define POT_PRESSURE 34      // Potentiometer 1: Discharge Pressure (ADC1)
#define POT_CURRENT 35       // Potentiometer 2: Motor Current (ADC1)
#define POT_VIBRATION 33     // Potentiometer 3: Vibration / Mechanical Fault Injector (ADC1)
#define POT_SPEED 32         // Potentiometer 4: Shaft Speed / Belt Slip Simulator (ADC1)

#define LED_NORMAL 2         // Green LED: Normal Operational State
#define LED_ADVISORY 4       // Red/Amber LED: Anomaly Advisory Flagged

// --------------------------------------------------
// Network & MQTT Broker Configuration
// --------------------------------------------------
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// Private Wokwi gateway host. The local browser demo runs without Wokwi.
const char* mqtt_server = "host.wokwi.internal";
const int mqtt_port = 1883;
const char* mqtt_topic = "factory/compressor/sensors";
const char* client_id = "ESP32_COMPRESSOR_UNIT01";

WiFiClient espClient;
PubSubClient client(espClient);
DHT dht(DHTPIN, DHTTYPE);

unsigned long lastPublish = 0;
const unsigned long publishInterval = 1000; // 1-second industrial telemetry cycle (1 Hz)
unsigned long sequenceNumber = 0;

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("\n========================================================");
  Serial.println("FACTORY EDGE: RECIPROCATING AIR COMPRESSOR TELEMETRY");
  Serial.println("Asset ID: COMPRESSOR_01 | Schema: 5-Sensor Section 11 Contract");
  Serial.println("========================================================");

  pinMode(LED_NORMAL, OUTPUT);
  pinMode(LED_ADVISORY, OUTPUT);
  digitalWrite(LED_NORMAL, HIGH);
  digitalWrite(LED_ADVISORY, LOW);

  pinMode(POT_PRESSURE, INPUT);
  pinMode(POT_CURRENT, INPUT);
  pinMode(POT_VIBRATION, INPUT);
  pinMode(POT_SPEED, INPUT);

  dht.begin();
  setup_wifi();

  client.setServer(mqtt_server, mqtt_port);
  Serial.println("Telemetry engine ready.");
}

void setup_wifi() {
  delay(10);
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected. IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Connection timeout (Simulated offline buffering).");
  }
}

void reconnect() {
  if (WiFi.status() != WL_CONNECTED) {
    setup_wifi();
  }

  while (!client.connected()) {
    Serial.print("[MQTT] Connecting to broker ");
    Serial.print(mqtt_server);
    Serial.print(" ... ");

    if (client.connect(client_id)) {
      Serial.println("SUCCESS (Connected)");
    } else {
      Serial.print("FAILED, rc=");
      Serial.print(client.state());
      Serial.println(" -> Retrying in 3s");
      delay(3000);
    }
  }
}

void readAndPublishTelemetry() {
  sequenceNumber++;

  // 1. Read Analog Potentiometers (0 to 4095 on ESP32 ADC)
  int raw_pressure = analogRead(POT_PRESSURE);
  int raw_current = analogRead(POT_CURRENT);
  int raw_vibration = analogRead(POT_VIBRATION);
  int raw_speed = analogRead(POT_SPEED);

  // 2. Physical Unit Conversions for 5 Sensor Categories
  // Pressure: 4.0 to 12.0 bar (Nominal 6.5 to 9.5 bar)
  float pressure_bar = map(raw_pressure, 0, 4095, 40, 120) / 10.0;

  // Motor Current: 10.0 to 32.0 A (Nominal 14.0 to 22.0 A)
  float current_amps = map(raw_current, 0, 4095, 100, 320) / 10.0;

  // Vibration: 0.05 to 0.80 g RMS (Nominal 0.05 to 0.30 g)
  float vib_base = map(raw_vibration, 0, 4095, 5, 80) / 100.0;
  float vib_jitter = (random(-10, 10) / 1000.0);
  float vibration_g = vib_base + vib_jitter;
  if (vibration_g < 0.01) vibration_g = 0.05;

  // Shaft Speed: 1200 to 1550 RPM (Nominal 1420 to 1480 RPM)
  float speed_rpm = map(raw_speed, 0, 4095, 1200, 1550);

  // Temperature via DHT22 (Nominal 60.0 to 95.0 °C)
  float temp_c = dht.readTemperature();
  if (isnan(temp_c)) {
    temp_c = 78.5 + (random(-15, 15) / 10.0);
  }

  // Generate ISO-8601-like timestamp
  char timeBuffer[32];
  unsigned long sec = millis() / 1000;
  snprintf(timeBuffer, sizeof(timeBuffer), "2026-11-16T%02lu:%02lu:%02luZ", (sec / 3600) % 24, (sec / 60) % 60, sec % 60);

  // 3. Serialize Standard Section 11 JSON Contract
#if ARDUINOJSON_VERSION_MAJOR >= 7
  JsonDocument doc;
#else
  StaticJsonDocument<512> doc;
#endif
  char msgId[32];
  snprintf(msgId, sizeof(msgId), "MSG-COMP-%06lu", sequenceNumber);

  doc["message_id"] = msgId;
  doc["machine_id"] = "COMPRESSOR_01";
  doc["timestamp"] = timeBuffer;
  doc["source"] = "WOKWI_SIMULATION";
  doc["sequence"] = sequenceNumber;

  doc["sensors"]["temperature"]["value"] = round(temp_c * 10) / 10.0;
  doc["sensors"]["temperature"]["unit"] = "°C";

  doc["sensors"]["vibration"]["value"] = round(vibration_g * 1000) / 1000.0;
  doc["sensors"]["vibration"]["unit"] = "g RMS";

  doc["sensors"]["pressure"]["value"] = round(pressure_bar * 10) / 10.0;
  doc["sensors"]["pressure"]["unit"] = "bar";

  doc["sensors"]["current"]["value"] = round(current_amps * 10) / 10.0;
  doc["sensors"]["current"]["unit"] = "A";

  doc["sensors"]["speed"]["value"] = round(speed_rpm);
  doc["sensors"]["speed"]["unit"] = "RPM";

  char jsonBuffer[512];
  serializeJson(doc, jsonBuffer);

  // 4. Publish over MQTT
  if (client.publish(mqtt_topic, jsonBuffer)) {
    Serial.println("\n[MQTT PUB SUCCESS] " + String(mqtt_topic));
    Serial.println(jsonBuffer);
    digitalWrite(LED_NORMAL, HIGH);
  } else {
    Serial.println("[MQTT PUB FAILED]");
    digitalWrite(LED_NORMAL, LOW);
  }
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastPublish >= publishInterval) {
    lastPublish = now;
    readAndPublishTelemetry();
  }
}
