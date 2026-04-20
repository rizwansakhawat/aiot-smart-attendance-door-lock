#include <Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

#define PIR_PIN       2
#define SERVO_PIN     9
#define GREEN_LED_PIN 6
#define RED_LED_PIN   7

Servo doorServo;

bool doorIsOpen = false;
unsigned long doorOpenedTime = 0;
unsigned long lastMotionSentTime = 0;
unsigned long verifyMessageShownAt = 0;

const unsigned long DOOR_OPEN_TIME = 6000;      // 6 seconds
const unsigned long MOTION_COOLDOWN = 1200;     // Avoid repeated MOTION spam
const unsigned long VERIFY_SCREEN_TIMEOUT = 4000; // Return to idle if no command arrives
const int SERVO_OPEN_ANGLE = 120;
const int SERVO_CLOSED_ANGLE = 0;

String serialBuffer = "";

void showWaitingScreen() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Waiting for");
  lcd.setCursor(0, 1);
  lcd.print("Motion...");
}

String cleanName(String name) {
  name.trim();

  // Keep display safe on 16x2 LCD and remove control characters.
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

  if (showLockedText) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("DOOR CLOSED");
    lcd.setCursor(0, 1);
    lcd.print("All Secure");
    delay(800);
  }

  showWaitingScreen();
  verifyMessageShownAt = 0;
}

void unlockDoor(String userName) {
  doorServo.write(SERVO_OPEN_ANGLE);
  doorIsOpen = true;
  doorOpenedTime = millis();

  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);
  verifyMessageShownAt = 0;

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Hi,Welcome!");
  lcd.setCursor(0, 1);

  String clean = cleanName(userName);
  if (clean.length() > 0) {
    lcd.print(clean);
    Serial.print("DOOR_UNLOCKED:");
    Serial.println(clean);
  } else {
    lcd.print("Welcome");
    Serial.println("DOOR_UNLOCKED");
  }
}

void deniedState() {
  doorServo.write(SERVO_CLOSED_ANGLE);
  doorIsOpen = false;
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
  verifyMessageShownAt = 0;

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("UNAUTHENTICATED");
  lcd.setCursor(0, 1);
  lcd.print("Access Blocked");

  Serial.println("DOOR_LOCKED");
  delay(1200);
  showWaitingScreen();
}

void deniedHoldState() {
  doorServo.write(SERVO_CLOSED_ANGLE);
  doorIsOpen = false;
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, HIGH);
  verifyMessageShownAt = 0;

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("UNAUTHENTICATED");
  lcd.setCursor(0, 1);
  lcd.print("Access Blocked");

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
    showWaitingScreen();
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

  if (cmd.startsWith("UNLOCK") || cmd.startsWith("unlock")) {
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

  Serial.print("UNKNOWN_CMD:");
  Serial.println(cmd);
}

void setup() {
  Serial.begin(9600);

  pinMode(PIR_PIN, INPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);

  doorServo.attach(SERVO_PIN);

  lcd.init();
  lcd.backlight();

  // Start with locked state and waiting screen.
  setLockedState(false);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Smart Door");
  lcd.setCursor(0, 1);
  lcd.print("System Ready");
  delay(2000);

  showWaitingScreen();
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

  // PIR only notifies motion; Python decides access based on face recognition.
  if (pirState == HIGH && !doorIsOpen && (millis() - lastMotionSentTime >= MOTION_COOLDOWN)) {
    Serial.println("MOTION");
    lastMotionSentTime = millis();
    verifyMessageShownAt = millis();

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Please Wait...");
    lcd.setCursor(0, 1);
    lcd.print("Verify Identity");
  }

  // If no unlock/denied command comes back, restore idle message automatically.
  if (!doorIsOpen && verifyMessageShownAt > 0 && (millis() - verifyMessageShownAt >= VERIFY_SCREEN_TIMEOUT)) {
    showWaitingScreen();
    verifyMessageShownAt = 0;
  }

  // Auto close after configured open time.
  if (doorIsOpen && millis() - doorOpenedTime >= DOOR_OPEN_TIME) {
    setLockedState(true);
    Serial.println("DOOR_LOCKED");
  }
}