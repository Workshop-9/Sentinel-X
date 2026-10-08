#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <time.h>

// ===================== CONFIGURATION =====================
// Wi-Fi et identifiants MQTT : dans secrets.h (ignoré par Git).
// Pour une nouvelle installation : copier secrets.example.h en secrets.h et le remplir.
#include "secrets.h"

const char* MQTT_HOST = "192.168.137.1";   // PC de l'équipe (hotspot + broker TLS)
const int   MQTT_PORT = 8883;              // MQTT chiffré (TLS)
const char* DEVICE_ID = "SX-001";
const char* TOPIC_TELEMETRY = "sentinel/SX-001/telemetry";
const char* TOPIC_CMD       = "sentinel/SX-001/cmd";
const char* TOPIC_STATUS    = "sentinel/SX-001/status";

// IP fixe + DNS (le DNS sert à la synchro de l'heure)
IPAddress ip(192,168,137,10), gateway(192,168,137,1), subnet(255,255,255,0), dns(192,168,137,1);

// Certificat de l'autorité (CA) du broker de l'équipe
const char CA_CERT[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIFFTCCAv2gAwIBAgIUJql+FUmFwchFW+pUKxS9PFXVB4MwDQYJKoZIhvcNAQEL
BQAwGjEYMBYGA1UEAwwPU2VudGluZWxYLUNBLUc5MB4XDTI2MTAwNzA4MDU1OVoX
DTI3MTAwNzA4MDU1OVowGjEYMBYGA1UEAwwPU2VudGluZWxYLUNBLUc5MIICIjAN
BgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEArzOE357eZPa2xiacRwaJwWAXayPO
9kT6+YiOEK0wEvxdeZavSQuIufTdyRFANjn7fc75zfJRK6xMw7E3zXMdI2LwL6pV
vuvUr5/+dvtzHFgLnT1ktRTJ+pYZhDsCSI6unyC73mDKfTbSBIu7RA/raFm0o4B2
PbmSOqrl38DbIxrnfLheDCEGuuwhTzuyuSBbju0qeVIoQtJpUaXWIm9PQ6VaN69r
mLP4LzYxq2c1sy7v+dWuubBfX0eEoeWpezOP3oQH52x9xm0IHwMTgGjX1praSn3P
8wziIjia47cwf2A7H9WbQ71aetgR2ydPDbW7zMlIPVei//kdqhNJy04FG0loTav7
t7OTNIzLypgzxKYaRxn2df1ZyiiWyG9JsxKFhIkmtSnU6qEAuN8l7spPh7+h3lqW
vMIe766Erc/OtTMiEIjtPClnP7W88nIEcg9/lwk2uvWqhg8KBAtEO9SLBJcTXtz1
MVAKxPWQMMhELSMXpPFeFxLp9Dz9rx83domOtj6eebCJWfd5cFXA8DsZ7Iv84Iau
JQtD/p/Y5qCUvD9+byEXHaC7bd/3JVedxaqk01RlFeR+hnpyUA2+2E9c/xYRofcj
mNVUdeixPweQUkxwr8eacKijRBZdQTvDMU9kVo7euBFvpVkwW3xKwdXvTbO3XJGG
32dvALwdRHr84CsCAwEAAaNTMFEwHQYDVR0OBBYEFIG+DEUs3RPhnu+D4B98mayC
a8PYMB8GA1UdIwQYMBaAFIG+DEUs3RPhnu+D4B98mayCa8PYMA8GA1UdEwEB/wQF
MAMBAf8wDQYJKoZIhvcNAQELBQADggIBAA29b8/tcie+y3Kt2mgbUmQgLD8+LTo1
F8mZunxWeuZicb7U4O0dHAp1xVZrT9AxiTygmyOK3Pxtn4R9Anxjq+abB4BgERqa
V9wDjT/B2wnQH5vYuLhezJcgCU97TmayMPushtw0fJzzNx0jxJJ5/s6BSajIS5S7
7bhiLAnMmUhswopvaG+TtJAniixUB0cxLyT/SENviOLgAgacpE5diX85Jj7oOtzB
Qoa8i6UPn/fTkJ1c5tO7gh5CL+ZC2TlgTlMPb0Ugrd/ajVsBfEAk5G48GGDA7ms7
NRBQl4wFZyXoTObyOtQqimrYup6Cwyoh9Z3eGCK1nu4OV80hG4g5/763geRqCQ2D
cTpCqO3peXtWjZq7i4lPMQHZW+wKjSjKkuxoDXIsSeoz3kKaZ4mBu1FEeBV+mawx
XDc0efHXJlh4Wn7aA2p9CYW0Hx/QuswDUjUuZnyK3d+HX91ye/XV21q5toPi6HqM
l367a+eaEvZfCUZ6M7JFTwJSXR6pimeIRi6LXQvhbcqJ1ECpjbQMI7LrxzeKrBjE
DSm0hUWDHbR/yPl2eADEnsJsQNG7b+OTQGAWeB4a1cNY9wAV/0ISJ9NFxfyFN4H4
L8V2WkJ2FHlqWLffUNMEXOjU/F2xgPU8mT2hNzKgb//vON38Nh2Igok7LGmOOIJ+
IfZsmzNl9oKE
-----END CERTIFICATE-----
)EOF";
// =========================================================

#define DHT_PIN    D5
#define PIR_PIN    D6
#define BUZZER_PIN D7
#define LED_VERTE  D0
#define LED_ROUGE  D8
#define GAS_PIN    A0

DHT dht(DHT_PIN, DHT22);
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
BearSSL::X509List caCert(CA_CERT);
WiFiClientSecure net;
PubSubClient mqtt(net);
bool oledOK = false;
bool alarmOn = false;
unsigned long lastSend = 0;

// Alarme : LED rouge ON, LED verte OFF (le son est géré dans loop)
void setAlarm(bool on) {
  alarmOn = on;
  digitalWrite(LED_ROUGE, on ? HIGH : LOW);
  digitalWrite(LED_VERTE, on ? LOW  : HIGH);
  if (!on) {
    noTone(BUZZER_PIN);
    digitalWrite(BUZZER_PIN, LOW);
  }
}

// Reçoit les commandes (flux 7)
void onMessage(char* topic, byte* payload, unsigned int len) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) return;
  const char* alarm = doc["alarm"];
  if (alarm) {
    setAlarm(strcmp(alarm, "on") == 0);
    Serial.printf(">>> Commande recue : alarm=%s\n", alarm);
  }
}

void oledMsg(const char* l1, const char* l2) {
  if (!oledOK) return;
  oled.clearDisplay();
  oled.setTextSize(1); oled.setTextColor(WHITE); oled.setCursor(0, 0);
  oled.println("SENTINEL-X  SX-001");
  oled.println(l1); oled.println(l2);
  oled.display();
}

void connectWiFi() {
  oledMsg("Connexion WiFi...", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.config(ip, gateway, subnet, dns);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.printf("\nWiFi OK : %s  |  MAC : %s\n",
                WiFi.localIP().toString().c_str(), WiFi.macAddress().c_str());
}

// L'heure est nécessaire pour vérifier la validité du certificat TLS
void syncTime() {
  oledMsg("Synchro heure...", "NTP");
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  unsigned long start = millis();
  time_t now = time(nullptr);
  while (now < 1700000000 && millis() - start < 10000) { delay(500); now = time(nullptr); }
  if (now < 1700000000) {
    Serial.println("NTP indisponible -> heure de secours utilisee");
    net.setX509Time(1791400000);   // 07/10/2026, après la création du certificat
  } else {
    Serial.printf("Heure OK (%lu)\n", (unsigned long)now);
  }
}

void connectMQTT() {
  while (!mqtt.connected()) {
    oledMsg("Connexion MQTT TLS", MQTT_HOST);
    Serial.print("MQTT TLS...");
    if (mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS, TOPIC_STATUS, 1, true, "offline")) {
      Serial.println(" connecte !");
      mqtt.publish(TOPIC_STATUS, "online", true);
      mqtt.subscribe(TOPIC_CMD);
      setAlarm(false);   // LED verte = tout va bien
    } else {
      Serial.printf(" echec (code %d)\n", mqtt.state());
      char err[80];
      if (net.getLastSSLError(err, sizeof(err))) Serial.printf("   Erreur TLS : %s\n", err);
      delay(3000);
    }
  }
}

void showOled(float t, float h, int gas, int motion) {
  if (!oledOK) return;
  oled.clearDisplay();
  oled.setTextSize(1); oled.setTextColor(WHITE); oled.setCursor(0, 0);
  oled.println("SENTINEL-X  SX-001");
  oled.print(WiFi.localIP()); oled.println(mqtt.connected() ? " TLS OK" : " TLS --");
  oled.drawLine(0, 18, 127, 18, WHITE);
  oled.setCursor(0, 22);
  oled.printf("Temp: %.1f C\n", t);
  oled.printf("Hum : %.0f %%\n", h);
  oled.printf("Gaz : %d\n", gas);
  oled.printf("Mvt : %s\n", motion ? "INTRUS !" : "RAS");
  if (alarmOn) oled.print("!!! ALARME !!!");
  oled.display();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_VERTE, OUTPUT);
  pinMode(LED_ROUGE, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  dht.begin();
  oledOK = oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);

  connectWiFi();
  syncTime();
  net.setTrustAnchors(&caCert);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  connectMQTT();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();

  // Sirène : bip-bip tant que l'alarme est active
  static unsigned long lastBeep = 0;
  static bool beepOn = false;
  if (alarmOn && millis() - lastBeep >= 300) {
    lastBeep = millis();
    beepOn = !beepOn;
    if (beepOn) tone(BUZZER_PIN, 2000);
    else noTone(BUZZER_PIN);
  }

  if (millis() - lastSend >= 2000) {   // toutes les 2 secondes
    lastSend = millis();
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    int gas = analogRead(GAS_PIN);
    int motion = digitalRead(PIR_PIN);

    JsonDocument doc;
    doc["device_id"] = DEVICE_ID;
    doc["ts"] = millis() / 1000;
    if (isnan(t)) doc["temp"] = nullptr; else doc["temp"] = round(t * 10) / 10.0;
    if (isnan(h)) doc["hum"]  = nullptr; else doc["hum"]  = round(h * 10) / 10.0;
    doc["gas"] = gas;
    doc["motion"] = motion;

    char buf[200];
    serializeJson(doc, buf);
    mqtt.publish(TOPIC_TELEMETRY, buf);
    Serial.println(buf);
    showOled(t, h, gas, motion);
  }
}