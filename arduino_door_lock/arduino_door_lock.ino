#include <Servo.h>

#define PIR_PIN 2
#define SERVO_PIN 9
#define GREEN_LED_PIN 6
#define RED_LED_PIN 7
#define BUZZER_PIN 5

Servo doorServo;

bool doorIsOpen = false;
bool pirLatchedHigh = false;
unsigned long doorOpenedTime = 0;
unsigned long lastMotionSentTime = 0;
unsigned long verifyMessageShownAt = 0;

const unsigned long DOOR_OPEN_TIME = 6000;         // 6 seconds
const unsigned long MOTION_COOLDOWN = 1200;        // Avoid repeated MOTION spam
const unsigned long VERIFY_SCREEN_TIMEOUT = 4000;  // Return to idle if no command arrives
const int SERVO_OPEN_ANGLE = 90;
const int SERVO_CLOSED_ANGLE = 0;
const bool BUZZER_USE_TONE = true;      // try passive buzzer (use tone())
const bool BUZZER_ACTIVE_HIGH = true;    // true = HIGH triggers buzzer, false = LOW triggers buzzer

String serialBuffer = "";

void buzzerOn() {
  digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_HIGH ? HIGH : LOW);
  Serial.print("BUZZER_PIN_STATE:ON|");
  Serial.println(digitalRead(BUZZER_PIN));
}

void buzzerOff() {
  digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_HIGH ? LOW : HIGH);
  Serial.print("BUZZER_PIN_STATE:OFF|");
  Serial.println(digitalRead(BUZZER_PIN));
}

void buzzOnce(int frequency, int durationMs) {
  Serial.print("BUZZER:");
  Serial.println(frequency);
  if (BUZZER_USE_TONE) {
    tone(BUZZER_PIN, frequency, durationMs);
    delay(durationMs + 20);
    noTone(BUZZER_PIN);
    buzzerOff();
    return;
  }

  buzzerOn();
  delay(durationMs);
  buzzerOff();
  delay(50);
}

void buzzUnlock() {
  Serial.println("BUZZER_UNLOCK_EVENT");
  buzzOnce(1800, 120);
}

void buzzDenied() {
  Serial.println("BUZZER_DENIED_EVENT");
  buzzOnce(900, 140);
  delay(80);
  buzzOnce(900, 140);
}

void buzzMotion() {
  Serial.println("BUZZER_MOTION_EVENT");
  buzzOnce(1400, 80);
}

String cleanName(String name) {
  name.trim();

  // Remove control characters so serial output stays clean.
  String out = "";
  for (unsigned int i = 0; i < name.length(); i++) {
    char c = name.charAt(i);
    if (c >= 32 && c <= 126) {
      out += c;
    }
  }

  if (out.length() > 16) {
    out = out.substring(0, 16);
  }

  return out;
}

void setLockedState(bool showLockedText) {
  doorServo.write(SERVO_CLOSED_ANGLE);
  doorIsOpen = false;
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
  verifyMessageShownAt = 0;

  if (showLockedText) {
    Serial.println("DOOR_CLOSED");
  }
}

void unlockDoor(String userName) {
  doorServo.write(SERVO_OPEN_ANGLE);
  doorIsOpen = true;
  doorOpenedTime = millis();

  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);
  verifyMessageShownAt = 0;

  buzzUnlock();

  String clean = cleanName(userName);
  if (clean.length() > 0) {
    Serial.print("DOOR_UNLOCKED:");
    Serial.println(clean);
  } else {
    Serial.println("DOOR_UNLOCKED");
  }
}

void deniedState() {
  doorServo.write(SERVO_CLOSED_ANGLE);
  doorIsOpen = false;
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
  verifyMessageShownAt = 0;

  buzzDenied();

  Serial.println("DOOR_LOCKED");
  delay(1200);
}

void deniedHoldState() {
  doorServo.write(SERVO_CLOSED_ANGLE);
  doorIsOpen = false;
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
  verifyMessageShownAt = 0;

  buzzDenied();

  Serial.println("DOOR_LOCKED");
}

void processCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) {
    return;
  }

  if (cmd.equalsIgnoreCase("PING")) {
    Serial.println("PONG");
    return;
  }

  if (cmd.equalsIgnoreCase("LOCK")) {
    setLockedState(true);
    Serial.println("DOOR_LOCKED");
    return;
  }

  if (cmd.equalsIgnoreCase("IDLE")) {
    verifyMessageShownAt = 0;
    Serial.println("IDLE_OK");
    return;
  }

  if (cmd.equalsIgnoreCase("DENIED")) {
    deniedState();
    return;
  }

  if (cmd.equalsIgnoreCase("DENIED_HOLD")) {
    deniedHoldState();
    return;
  }

  if (cmd.startsWith("UNLOCK")) {
    String userName = "";
    int sepIndex = cmd.indexOf(':');
    if (sepIndex < 0) {
      sepIndex = cmd.indexOf('|');
    }
    if (sepIndex >= 0 && sepIndex + 1 < (int)cmd.length()) {
      userName = cmd.substring(sepIndex + 1);
    }

    unlockDoor(userName);
    return;
  }

  // Ignore unknown commands to keep serial output low.
}

void setup() {
  Serial.begin(9600);
  delay(500);  // Give serial connection time to establish
  Serial.println("===== ARDUINO BOOTED =====");

  pinMode(PIR_PIN, INPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  buzzerOff();

  doorServo.attach(SERVO_PIN);

  // Start with a locked door state.
  setLockedState(false);

  // Startup self-test beep so buzzer wiring can be verified quickly.
  Serial.println("===== BUZZER STARTUP TEST =====");
  
  // Direct pin test - toggle 5 times to verify pin is working
  Serial.println("DIRECT PIN TEST:");
  for (int i = 0; i < 5; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(300);
    Serial.print("PIN HIGH: ");
    Serial.println(digitalRead(BUZZER_PIN));
    
    digitalWrite(BUZZER_PIN, LOW);
    delay(300);
    Serial.print("PIN LOW: ");
    Serial.println(digitalRead(BUZZER_PIN));
  }
  
  Serial.println("===== BUZZER BEEP TEST =====");
  for (int i = 0; i < 3; i++) {
    buzzOnce(1500, 200);
    delay(150);
  }
  Serial.println("===== TEST COMPLETE =====" );

  Serial.println("READY");
}

void loop() {
  // Read serial commands from Python one line at a time.
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        processCommand(serialBuffer);
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
      if (serialBuffer.length() > 80) {
        serialBuffer = "";
      }
    }
  }

  int pirState = digitalRead(PIR_PIN);

  // Trigger motion once per new HIGH edge instead of repeating while PIR stays HIGH.
  if (pirState == HIGH) {
    if (!pirLatchedHigh && !doorIsOpen && (millis() - lastMotionSentTime >= MOTION_COOLDOWN)) {
      buzzMotion();
      Serial.println("MOTION");
      lastMotionSentTime = millis();
      verifyMessageShownAt = millis();
      Serial.println("VERIFY_IDENTITY");
    }
    pirLatchedHigh = true;
  } else {
    pirLatchedHigh = false;
  }

  // If no unlock/denied command comes back, restore idle message automatically.
  if (!doorIsOpen && verifyMessageShownAt > 0 && (millis() - verifyMessageShownAt >= VERIFY_SCREEN_TIMEOUT)) {
    Serial.println("VERIFY_TIMEOUT");
    verifyMessageShownAt = 0;
  }

  // Auto close after configured open time.
  if (doorIsOpen && millis() - doorOpenedTime >= DOOR_OPEN_TIME) {
    setLockedState(true);
    Serial.println("DOOR_LOCKED");
  }
}