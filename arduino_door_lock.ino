/*
 * ═══════════════════════════════════════════════════════════════
 * AIoT Smart Attendance & Door Lock System
 * Arduino Code - Basic Version
 * ═══════════════════════════════════════════════════════════════
 * 
 * Hardware:
 * - Arduino Uno
 * - PIR Motion Sensor (Pin 2)
 * - Servo Motor (Pin 9)
 * 
 * Communication: Serial (USB) with Python
 * 
 * ══════════════════════════════════════��════════════════════════
 */

#include <Servo.h>

// ═══════════════════════════════════════════════════════════════
// PIN DEFINITIONS
// ═══════════════════════════════════════════════════════════════
#define PIR_PIN 2        // PIR Motion Sensor
#define SERVO_PIN 9      // Servo Motor (Door Lock)

// ═══════════════════════════════════════════════════════════════
// SERVO POSITIONS
// ═══════════════════════════════════════════════════════════════
#define DOOR_LOCKED 0      // Servo position when locked
#define DOOR_UNLOCKED 90   // Servo position when unlocked

// ═══════════════════════════════════════════════════════════════
// TIMING SETTINGS
// ═══════════════════════════════════════════════════════════════
#define DOOR_OPEN_TIME 5000      // Door stays open for 5 seconds
#define MOTION_COOLDOWN 3000     // Wait 3 seconds before next detection
#define SERIAL_TIMEOUT 10000     // Wait 10 seconds for Python response

// ═══════════════════════════════════════════════════════════════
// OBJECTS
// ═══════════════════════════════════════════════════════════════
Servo doorServo;

// ═══════════════════════════════════════════════════════════════
// VARIABLES
// ═══════════════════════════════════════════════════════════════
bool motionDetected = false;
bool doorIsOpen = false;
unsigned long lastMotionTime = 0;
unsigned long doorOpenedTime = 0;
String serialCommand = "";

// ═══════════════════════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════════════════════
void setup() {
    // Initialize Serial Communication
    Serial.begin(9600);
    
    // Initialize PIR Sensor
    pinMode(PIR_PIN, INPUT);
    
    // Initialize Servo
    doorServo.attach(SERVO_PIN);
    lockDoor();  // Start with door locked
    
    // Startup message
    Serial.println("═══════════════════════════════════════════");
    Serial.println("   AIoT Smart Door Lock System Started");
    Serial.println("═══════════════════════════════════════════");
    Serial.println("STATUS:READY");
    
    // Wait for PIR sensor to stabilize (30 seconds recommended)
    Serial.println("INFO:PIR sensor stabilizing...");
    delay(5000);  // Reduced to 5 seconds for testing
    Serial.println("INFO:System ready!");
}

// ═══════════════════════════════════════════════════════════════
// MAIN LOOP
// ═══════════════════════════════════════════════════════════════
void loop() {
    // Check for commands from Python
    checkSerialCommands();
    
    // Check PIR sensor for motion
    checkMotionSensor();
    
    // Auto-close door after timeout
    checkDoorTimeout();
    
    delay(100);  // Small delay for stability
}

// ═══════════════════════════════════════════════════════════════
// CHECK SERIAL COMMANDS FROM PYTHON
// ═══════════════════════════════════════════════════════════════
void checkSerialCommands() {
    while (Serial.available() > 0) {
        char c = Serial.read();
        
        if (c == '\n') {
            // Process command
            processCommand(serialCommand);
            serialCommand = "";
        } else {
            serialCommand += c;
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// PROCESS COMMANDS
// ═══════════════════════════════════════════════════════════════
void processCommand(String cmd) {
    cmd.trim();  // Remove whitespace
    
    if (cmd == "UNLOCK") {
        // Access granted - unlock door
        unlockDoor();
        Serial.println("RESPONSE:DOOR_UNLOCKED");
    }
    else if (cmd == "LOCK") {
        // Lock door
        lockDoor();
        Serial.println("RESPONSE:DOOR_LOCKED");
    }
    else if (cmd == "DENIED") {
        // Access denied - keep door locked
        Serial.println("RESPONSE:ACCESS_DENIED");
        // Future: Add buzzer alert here
    }
    else if (cmd == "STATUS") {
        // Report current status
        if (doorIsOpen) {
            Serial.println("RESPONSE:DOOR_OPEN");
        } else {
            Serial.println("RESPONSE:DOOR_LOCKED");
        }
    }
    else if (cmd == "PING") {
        // Connection test
        Serial.println("RESPONSE:PONG");
    }
    else {
        Serial.println("RESPONSE:UNKNOWN_COMMAND");
    }
}

// ═══════════════════════════════════════════════════════════════
// CHECK MOTION SENSOR
// ═══════════════════════════════════════════════════════════════
void checkMotionSensor() {
    // Check cooldown period
    if (millis() - lastMotionTime < MOTION_COOLDOWN) {
        return;
    }
    
    // Don't detect motion if door is already open
    if (doorIsOpen) {
        return;
    }
    
    // Read PIR sensor
    int pirState = digitalRead(PIR_PIN);
    
    if (pirState == HIGH && !motionDetected) {
        // Motion detected!
        motionDetected = true;
        lastMotionTime = millis();
        
        // Notify Python
        Serial.println("MOTION:DETECTED");
    }
    else if (pirState == LOW) {
        motionDetected = false;
    }
}

// ═══════════════════════════════════════════════════════════════
// DOOR CONTROL FUNCTIONS
// ═══════════════════════════════════════════════════════════════
void unlockDoor() {
    doorServo.write(DOOR_UNLOCKED);
    doorIsOpen = true;
    doorOpenedTime = millis();
    Serial.println("INFO:Door unlocked");
}

void lockDoor() {
    doorServo.write(DOOR_LOCKED);
    doorIsOpen = false;
    Serial.println("INFO:Door locked");
}

// ═══════════════════════════════════════════════════════════════
// AUTO-CLOSE DOOR AFTER TIMEOUT
// ═════════════════════════════════════════════════════���═════════
void checkDoorTimeout() {
    if (doorIsOpen && (millis() - doorOpenedTime >= DOOR_OPEN_TIME)) {
        lockDoor();
        Serial.println("INFO:Door auto-locked");
    }
}