/*
* qwstPad.cpp
* 
* This file is part of the QwstPad library for Arduino.
* It provides functionality to interface with the QwstPad hardware.
* Created by Paulus Schulinck (Github handle: @PaulskPt).
* Date: 2025-08-10
* License: MIT License
* The QwstPad library is used to interface with the Pimoroni Qw/ST Pad (I2C Game Controller) board.
* Product info: https://shop.pimoroni.com/products/qwst-pad?variant=53514400596347
* This library is ported by me from the Pimoroni qwstpad-micropython library.
* See:  https://github.com/pimoroni/qwstpad-micropython/blob/main/src/qwstpad.py
* 
*/
#include "qwstpad.h"
#include <Arduino.h>
#include <HardwareSerial.h>  // Add this for Serial support
#include <cstdint>
#include <vector>
#include <stdexcept>  // for std::invalid_argument
#include <algorithm>  // for std::find
#include <cstdarg>    // for va_list, va_start, va_end
#include <iostream>   // same

bool padInitialized = false;  // Flag to indicate if the pad is initialized

extern std::vector<padConfig> padConfigs;


// Global definition of __config
padConfig* __config = nullptr;

std::vector<padConfig> padConfigs = {
    {
        .padID = 0,
        .logic = ACTIVE_HIGH,
        .buttonPins = {}
    },
    {
        .padID = 1,
        .logic = ACTIVE_HIGH,
        .buttonPins = {}
    },
    {
        .padID = 2,
        .logic = ACTIVE_HIGH,
        .buttonPins = {}
    },
    {
        .padID = 3,
        .logic = ACTIVE_HIGH,
        .buttonPins = {}
    }
};
/*
// This is an alternative way to define padConfigs
std::vector<padConfig> padConfigs = {
    {0, ACTIVE_HIGH, {}},
    {1, ACTIVE_HIGH, {}},
    {2, ACTIVE_HIGH, {}},
    {3, ACTIVE_HIGH, {}}
};
*/

const std::unordered_map<std::string, uint8_t> BUTTON_MAPPING = {
    {"U", 0x1},  // Value: 1, 2, 3, 4, 5, B, C, D, E, F 
    {"L", 0x2}, 
    {"R", 0x3}, 
    {"D", 0x4},
    {"M", 0x5}, // Minus
    {"P", 0xB}, // Plus
    {"B", 0xC}, 
    {"Y", 0xD},
    {"A", 0xE}, 
    {"X", 0xF}
};


const std::vector<uint8_t> LED_MAPPING = {0x6, 0x7, 0x9, 0xA};

// Constructor: initializes mappings and internal states
QwstPad::QwstPad(uint8_t address) {
    init(__i2c, address, true);
}

QwstPad::QwstPad(TwoWire* i2c_port, uint8_t address,  bool show_address) {
    // bool show_address = true;
    init(i2c_port, address, show_address); // This sets __padID and __config

#ifdef MY_DEBUG
    Serial.print("Constructed pad at address: 0x");
    Serial.println(address, HEX);
#endif
    
}

void QwstPad::init(TwoWire* i2c_port, uint8_t address = DEFAULT_ADDRESS, bool show_address=true) {
    __i2c = i2c_port;
    __config = nullptr;
    __padID = -1;
    __led_states = 0; // defined in qwstpad.h
    __last_button_states.clear();
    padInitialized = false;

    if (!isValidAddress(address)) {
        Serial.print("ERROR: Invalid address 0x");
        Serial.println(address, HEX);
        return;
    }
    
    __address = address;
    __padID = getpadIDFromAddress(address);

#ifndef MY_DEBUG
    Serial.print(F("QwstPad::init(): "));
    Serial.print(F("Initialized pad with __padID: "));
    Serial.print(__padID);
    Serial.print(F(" at address: 0x"));
    Serial.println(__address, HEX);
#endif
    for (const auto& [key, _] : BUTTON_MAPPING) {
        __last_button_states[key] = false;
    }
    
    std::vector<std::pair<std::string, uint8_t>> buttonList;

    for (const auto& pair : BUTTON_MAPPING) {
        buttonList.push_back({pair.first, pair.second});
    }
    makeButtons(buttonList);

    /* Using const padConfig* means you're promising not to modify 
       the contents of the padConfig through this pointer. 
       If you do need to modify it, just remove the const: 
    */
    __config = nullptr;  // Reset __config to nullptr before searching
    // Search for the padConfig that matches __padID
    for (size_t i = 0; i < padConfigs.size(); ++i) {
        if (padConfigs[i].padID == __padID) {
            __config = &padConfigs[i];  // ✅ Safe: pointer to actual container element
            __config->buttonPins.clear();
            for (const auto& [key, value] : BUTTON_MAPPING) {
                __config->buttonPins[key] = static_cast<int>(value);  // Store button pin indices
            }
            break;
        }
    }
    if (!__config) {
        Serial.print(F("Pad ID not found: "));
        Serial.println(__padID);
        //while (true);  // Halt the CPU
        __config = nullptr;
        __padID = -1;
        Serial.println(F("Warning: No config found for pad"));
        return;  // Exit init() early
    }
    else {
#ifdef MY_DEBUG
        Serial.print(F("Config found for pad:"));
        Serial.print(__config->padID);
        Serial.print(F(", logic: "));
        Serial.println(__config->logic);
#endif
        padInitialized = true;  // Set a flag to indicate successful initialization
    }
    clear_button_states();

    if (show_address)
        set_leds(address_code());
}

void QwstPad::deinit() {
    __config = nullptr;
    __padID = -1;
    __led_states = 0;
    __last_button_states.clear();
    padInitialized = false;
}

void QwstPad::begin() {
#ifdef MY_DEBUG
    Serial.print(F("QwstPad::begin(): entered for "));
    pr_PadID();
    Serial.println();
#endif
    setupTCA9555();

    // Turn off all LEDs initially
    set_leds(false);
}

void QwstPad::setupTCA9555() {
#ifdef MY_DEBUG
    Serial.print(F("QwstPad::setupTCA9555(): entered for "));
    pr_PadID();
    Serial.println();
#endif
  // Set pin directions: 1 = input, 0 = output
  // Port 0 (lower byte): bits 0–5 = inputs (buttons), bits 6–7 = outputs (LEDs)
  // Port 1 (upper byte): bits 8–10 = outputs (LEDs), bits 11–15 = inputs (buttons)
  uint16_t config = 0b11111001'00111111;
  writeRegister16(__address, CONFIG_PORT0, config);

  // Set polarity inversion: 1 = inverted
  // Invert button bits only
  uint16_t polarity = 0b11111000'00111111;

  writeRegister16(__address, POLARITY_PORT0, polarity);

  // Set initial output state for LEDs (active-low logic)
  // 1 = off, 0 = on → so we start with all LEDs off
  uint16_t output = 0b00000110'11000000;
  writeRegister16(__address, OUTPUT_PORT0, output);
}

ButtonDescriptor QwstPad::makeButtonDescriptor(const std::string& label, uint8_t pinIdx) {
    static constexpr const char txt1[] PROGMEM = "Unknown button label: ";
    auto it = BUTTON_MAPPING.find(label);
    if (it == BUTTON_MAPPING.end()) {
        throw std::runtime_error(txt1 + label);
    }
    return {label, it->second, pinIdx};
}

std::vector<ButtonDescriptor> QwstPad::makeButtons(const std::vector<std::pair<std::string, uint8_t>>& labelBitIndexPairs) {
    std::vector<ButtonDescriptor> buttons;
    for (const auto& [label, bitIndex] : labelBitIndexPairs) {
        buttons.push_back({label, BUTTON_MAPPING.at(label), bitIndex});
    }
    return buttons;
}

bool QwstPad::IsInitialized() const {
    return padInitialized;  // Check if the pad is initialized
}

// Default version for most use cases (160-byte buffer)
void QwstPad::serialPrintf(const char* format, ...) const {
    char buf[160];
    va_list args;
    va_start(args, format);
    vsnprintf(buf, sizeof(buf), format, args);
    va_end(args);
    Serial.print(buf);
}

void QwstPad::printBinary(uint16_t num, bool fancy = false) const {
    if (fancy)
        Serial.print(F("  | "));
    for (int i = sizeof(uint16_t) * 8 - 1; i >= 1; i--) {  // 15 bits for 16-bit number
        serialPrintf("%d", (num >> i) & 1);
        if (i == 11 || i == 6) { // Add space every 4 bits for readability)
            if (fancy) {
                Serial.print(F(" | "));  // Add space every 5 bits for readability
            } else {
                Serial.print(F(" "));  // Add space every 5 bits for readability
            }
        }
    }
    if (fancy) {
        Serial.print(F(" | "));
    }
}

bool QwstPad::isValidAddress(uint8_t addr) {
    for (uint8_t i = 0; i < sizeof(ADDRESSES); i++) {
        if (ADDRESSES[i] == addr) return true;
    }
    return false;
}

void QwstPad::clear_button_states() {
    for (const auto& [key, _] : BUTTON_MAPPING) {
        __button_states[key] = false;
        __last_button_states[key] = false;
    }
}

bool QwstPad::isConnected() {
    __i2c->beginTransmission(__address);
    return __i2c->endTransmission() == 0;  // 0 = success, device responded
}

uint8_t QwstPad::getAddress() const {
    return __address;
}

uint8_t QwstPad::getpadIDFromAddress(uint8_t address) {
    switch (address) {
        case 0x21: return 0;
        case 0x23: return 1;
        case 0x25: return 2;
        case 0x27: return 3;
        default:   return -1;  // Invalid
    }
}

uint16_t QwstPad::address_code() const {
    // Returns a bitmask representing the pad's I2C address,
    // used for controlling LEDs via set_leds()
    constexpr size_t num_addresses = sizeof(ADDRESSES) / sizeof(ADDRESSES[0]);
#ifdef MY_DEBUG
    Serial.print(F("QwstPad::address_code(): "));
    Serial.print(F("num_addresses: "));
    Serial.print(num_addresses);
    Serial.print(F(", __address: 0x"));
    Serial.println(__address, HEX);
#endif
    for (size_t i = 0; i < num_addresses; ++i) {
        if (ADDRESSES[i] == __address) {
            return __change_bit(0x0000, i, true);
        }
    }
    throw std::runtime_error("Address not found in ADDRESSES");
}

padConfig* QwstPad::getConfig() {
    return __config;
}

std::map<std::string, bool> QwstPad::read_buttons() {
    update();  // Sync hardware
    return __button_states;
}

std::map<std::string, bool> QwstPad::read_buttons2() {
    uint16_t state = __reg_read_uint16(__i2c, __address, INPUT_PORT0);
    bool rawBit = false;
    bool pressed = false;
    
    for (const auto& [key, index] : BUTTON_MAPPING) {
        rawBit = __get_bit(state, index);
        // ---------- IMPORTANT LOGIC HANDLING ----------
        if (__config->logic == ACTIVE_LOW)
            pressed = !rawBit;
        else if (__config->logic == ACTIVE_HIGH)
            pressed = rawBit;
        // -----------------------------------------------
        __button_states[key] = pressed;
     }
     return __button_states;
}

void QwstPad::pr_PadID() const {
    serialPrintf(PSTR("Pad %d"), __padID+1);
}

void QwstPad::printAllPadConfigs() const {
  Serial.println(F("📦 Pad Configurations:"));

  for (const auto& cfg : padConfigs) {
    Serial.print(F("Pad ID: "));
    Serial.println(cfg.padID);

    Serial.print(F("  Logic Type: "));
    Serial.println(cfg.logic == ACTIVE_LOW ? "ACTIVE_LOW" : "ACTIVE_HIGH");

    Serial.print(F("  Button Pins: "));
    if (cfg.buttonPins.empty()) {
      Serial.println(F("(none)"));
    } else {
      for (const auto& [key, pin] : cfg.buttonPins) {
        Serial.print("'");
        Serial.print(key.c_str());
        Serial.print("' → ");
        Serial.print(pin);
        Serial.print("  ");
      }
      Serial.println();
    }

    Serial.println(F("---------------------------"));
  }
}

// getButtonBitfield() → normal bitfield
uint16_t QwstPad::getButtonBitfield(bool show, bool fancy = false) {
    static constexpr const char txt0[] PROGMEM = "QwstPad::getButtonBitfield(): ";
    // Apply inversion internally based on config
    //bool invert = (__config->logic == ACTIVE_LOW);
    uint16_t result = 0;
    bool pressed = false;
 
#ifdef MY_DEBUG
    Serial.print(txt0);
    pr_PadID();
    if (__config != nullptr) {
        Serial.print(", pad logic: ACTIVE_");
        Serial.println(__config->logic == ACTIVE_LOW ? "LOW" : "HIGH");
    }
#endif
    std::map<std::string, bool> __btn_states;
    // Note: read_buttons calls update() internally!
    // and update() already takes care of the logic inversion
    // based on the pad's logic type (ACTIVE_LOW or ACTIVE_HIGH)
    __btn_states = read_buttons2();  // local variable to hold button states
#ifdef MY_DEBUG
    Serial.print(txt0);
    pr_PadID();
#endif
    uint8_t index = 0;
    for (const auto& entry : __btn_states) {
        if (__padID >= 0 && __padID < MAX_PADS)
            pressed = entry.second;
        else {
            Serial.println(F("ERROR: Invalid padID: "));
            Serial.println(__padID);
            pressed = false;  // Default to false if logic is invalid
        }
        if (pressed) { // only process pressed buttons
#ifdef MY_DEBUG
            pr_PadID();
            Serial.print(", key: ");
            Serial.print(entry.first.c_str());
            Serial.print(" -> ");
#endif
            index = BUTTON_MAPPING.at(entry.first);  // Get the bit index from mapping
#ifdef MY_DEBUG
            Serial.print(F("Bit index: "));
            Serial.print(index);
            Serial.print(F(", is "));
            Serial.println(pressed ? "pressed" : "not pressed");
#endif

#ifdef MY_DEBUG
            Serial.print(F("bit_value = "));
            Serial.println(pressed);
#endif
            result |= (1 << index);
        }
    }
   
    if (result > 0) {
        if (show) {
            static constexpr const char bf[] PROGMEM = "bitfield";
            if (fancy) {
                static constexpr const char hdg[] PROGMEM =      "  | PadL  | LEDs  | PadR  |";
                static constexpr const char bits_hdg[] PROGMEM = "  |b15~b11|b10~b6 | b5~b0 |";
                //Serial.println(txt0);
                pr_dashBar();
                Serial.println(hdg);
                pr_dashBar();
                Serial.println(bits_hdg);
                pr_dashBar();
                printBinary(result, fancy);
                Serial.print(F("<- "));
                pr_PadID();
                Serial.print(F(" "));
                Serial.println(bf);
                pr_dashBar();
            } else {
                serialPrintf(PSTR("%s "),bf);
                printBinary(result, fancy);
                Serial.println();
            }
        }
    }

    return result;
}

int8_t QwstPad::getFirstPressedButtonBitIndex() {
    std::map<std::string, bool> __btn_states = read_buttons();  // Update button states
    bool pressed = false;

    for (const auto& entry : __btn_states) {
        if (__padID >= 0 && __padID < MAX_PADS)
            pressed = entry.second;
        else {
            Serial.print(F("ERROR: Invalid padID"));
            Serial.println(__padID);
            continue;
        }
        if (pressed) {
            auto it = BUTTON_MAPPING.find(entry.first);
            if (it != BUTTON_MAPPING.end()) {
                uint8_t index = it->second;
#ifdef MY_DEBUG
                Serial.print(F("First pressed button bit index: "));
                Serial.println(index);
#endif
                return index;
            } else {
                Serial.print(F("Button name not found in mapping: "));
                Serial.println(entry.first.c_str());
                return -1; // Not found
            }
        }
    }
    return -1; // No button pressed
}

std::string QwstPad::getFirstPressedButtonName() {
    std::map<std::string, bool> __btn_states = read_buttons();  // Update button states
    bool pressed = false;

    for (const auto& entry : __btn_states) {
        if (__padID >= 0 && __padID < MAX_PADS)
            pressed = entry.second;
        else {
            Serial.print(F("ERROR: Invalid padID"));
            Serial.println(__padID);
            continue;
        }
        if (pressed) {
#ifdef MY_DEBUG
            pr_PadID();
            Serial.print(F(", first pressed key: "));
            Serial.println(entry.first.c_str());
#endif
            return entry.first;  // Return as std::string
        }
    }

    return std::string();  // No button pressed
}


void QwstPad::pr_spc(uint8_t cnt) const {
    for (uint8_t i = 0; i < cnt; i++) {
        Serial.print(F(" "));
    }
}

void QwstPad::pr_dashBar() const {
    Serial.println(F("  +-------+-------+-------+"));
}

bool QwstPad::isButtonPressed(const std::string& key) {
    if (!__config) return false;

    auto it = __config->buttonPins.find(key);
    if (it == __config->buttonPins.end()) {
        Serial.print(F("WARNING: Button key not found: "));
        Serial.println(key.c_str());
        return false;
    }

    int index = it->second;
    bool raw = readRawPin(index);
    return (__config->logic == ACTIVE_LOW) ? !raw : raw;
}


bool QwstPad::wasPressed(const std::string& key) const {
    auto lastIt = __last_button_states.find(key);
    auto currIt = __button_states.find(key);

    if (lastIt != __last_button_states.end() && currIt != __button_states.end()) {
        return !lastIt->second && currIt->second;
    }

    return false;
}

int8_t QwstPad::getLogicType() {
    if (__config) {
        return static_cast<int8_t>(__config->logic);
    }
    return -1;  // Return -1 if config is not set
}

int8_t QwstPad::setLogicType(LogicType type) {
    if (__config && (type == ACTIVE_LOW || type == ACTIVE_HIGH)) {
        __config->logic = type;  // ✅ Now allowed
    }

    Serial.print(F("QwstPad::setLogicType(): "));
    pr_PadID();

    if (__config) {
        Serial.print(F(", logic type set to: "));
        Serial.println(__config->logic == ACTIVE_LOW ? "ACTIVE_LOW" : "ACTIVE_HIGH");
        return static_cast<int8_t>(__config->logic);
    }
    return UNKNOWN;
}

std::vector<ButtonEvent> QwstPad::pollEvents() {
    static constexpr const char txt0[] PROGMEM = "QwstPad::pollEvents(): ";
    std::vector<ButtonEvent> events;

    for (const auto& [key, index] : __config->buttonPins) {
        uint16_t state = __reg_read_uint16(__i2c, __address, INPUT_PORT0);
        bool rawBit = __get_bit(state, index);  // Read raw bit from hardware
        bool pressed = (__config->logic == ACTIVE_LOW) ? !rawBit : rawBit;
#ifdef MY_DEBUG
        if (__address == ALT_ADDRESS_1 && rawBit == 1) {
            Serial.print(txt0);
            pr_PadID();
            Serial.print(F(", __address = 0x"));
            Serial.print(__address, HEX);
            Serial.print(F(", key = "));
            Serial.print(key.c_str());
            Serial.print(F(", index = "));
            Serial.println(index);
            Serial.print(txt0);
            pr_PadID();
            Serial.print(F(", state = 0b"));
            printBinary(state);
            //Serial.print(state, HEX);
            Serial.print(F(", rawBit = "));
            Serial.print(rawBit);
            Serial.print(F(", pressed = "));
            Serial.println(pressed ? "PRESSED" : "RELEASED");
        }
#endif
        if (pressed && wasPressed(key)) {
            events.push_back({key, PRESSED});
        } else if (!pressed && wasReleased(key)) {
            events.push_back({key, RELEASED});
        }
    }
    return events;
}

uintptr_t QwstPad::debugConfigPointer() const {
    return reinterpret_cast<uintptr_t>(__config);
}

bool QwstPad::debugPrintStates() const {
  bool result = false;
  Serial.println("Current button states:");
  for (const auto& [key, state] : __button_states) {
    Serial.print(key.c_str());
    Serial.print(": ");
    Serial.print(state);
    if (state) {
      result = true;  // At least one button is pressed
    }
    Serial.print(F(", "));
  }
  Serial.println();

  Serial.println("Previous button states:");
  for (const auto& [key, state] : __last_button_states) {
    Serial.print(key.c_str());
    Serial.print(": ");
    Serial.print(state);
    Serial.print(F(", "));
  }
  Serial.println();
  return result;  // Return true if any button is pressed
}

void QwstPad::update() {
    static constexpr const char txt0[] PROGMEM = "QwstPad::update(): ";
    __last_button_states = __button_states;  // Save previous state

#ifdef MY_DEBUG
    Serial.print(txt0);
    pr_PadID();
    Serial.print(F("Raw state value: 0b"));
    printBinary(state);
    Serial.println();
#endif
    __button_states.clear();
    uint8_t buttonSum = 0;

    uint16_t state = __reg_read_uint16(__i2c, __address, INPUT_PORT0);

#ifdef MY_DEBUG
    if (__padID == 1) {
        Serial.print(txt0);
        pr_PadID();
        Serial.print(F(", state = "));
        printBinary(state, false);
        Serial.println();
        if (state >0)
           delay(3000);
    }
#endif
    for (const auto& [key, index] : BUTTON_MAPPING) {
#ifdef MY_DEBUG
        Serial.print(txt0);
        pr_PadID();
        Serial.print(F(", Key length: "));
        Serial.print(key.length());
        Serial.print(F(", key = \'"));
        if (key.length()) {
            Serial.print(key.c_str());
            Serial.println(F("\'"));
            //Serial.println(F("Safe key print\'TEST\'"));
        } else
            Serial.print(F("[EMPTY]"));
        Serial.print(F("Checking index validity: index = "));
        Serial.println(index);
#endif
        if (index >= 16) {
            Serial.println(F("ERROR: Index out of range for 16-bit state."));
            return;
        }
        else {
            bool rawBit = false;
            rawBit = __get_bit(state, index);
#ifdef MY_DEBUG
            Serial.print("Bit result = ");
            Serial.println(rawBit);
#endif
            bool pressed = false;
#ifdef MY_DEBUG
            Serial.println(F("Checking config pointer..."));
#endif
            if (__config == nullptr) {
                Serial.println(F("ERROR: __config is null!"));
                //return; // or handle error
            }
            else {
#ifdef MY_DEBUG
                Serial.println(F("Config pointer is valid"));
                Serial.print("Pad logic: ");
                Serial.println(__config->logic == ACTIVE_LOW ? "ACTIVE_LOW" : "ACTIVE_HIGH");
#endif
                // ---------- IMPORTANT LOGIC HANDLING ----------
                if (__config->logic == ACTIVE_LOW)
                    pressed = !rawBit;
                else if (__config->logic == ACTIVE_HIGH)
                    pressed = rawBit;
                // -----------------------------------------------
                buttonSum ^= pressed;  // Accumulate state toggles
#ifdef MY_DEBUG
                Serial.print(txt0);
                pr_PadID();
                Serial.print(" rawBit for ");
                Serial.print(key.c_str());
                Serial.print(": ");
                Serial.println(rawBit);

                Serial.print(F("pressed = "));
                Serial.println(pressed);
                Serial.print(F("Writing to key: "));
                Serial.println(key.c_str());
#endif          
                __button_states[key] = pressed;
            }
        }
    }
#ifdef MY_DEBUG
    Serial.print(F("Checksum of pressed states: "));
    Serial.println(buttonSum);
#endif
}

bool QwstPad::readRawPin(int index) {
    if (index < 0 || index >= 16) {
        Serial.println(F("ERROR: Index out of range for 16-bit state."));
        return false;
    }

    uint16_t state = __reg_read_uint16(__i2c, __address, INPUT_PORT0);
    return __get_bit(state, index);
}

bool QwstPad::buttonChanged(const std::string& key) {
    return __button_states[key] != __last_button_states[key];
}

bool QwstPad::wasReleased(const std::string& key) const {
    auto lastIt = __last_button_states.find(key);
    auto currIt = __button_states.find(key);

    if (lastIt != __last_button_states.end() && currIt != __button_states.end()) {
        return lastIt->second && !currIt->second;
    }

    return false;
}

void QwstPad::set_led(uint8_t index, bool state) {
    // LED index is 1-based (1 to 4)
#ifdef MY_DEBUG
    pr_PadID();
    Serial.print(F(", setting LED "));
    Serial.print(index);
    Serial.print(F(" to state: "));
    Serial.println(state ? "ON" : "OFF");
#endif
    if (index < 1 || index > NUM_LEDS) {
        Serial.println(F("LED index out of range (1-4)"));
        return;
    }
    // Update internal LED state bitfield (4 bits)
    __led_states = __change_bit(__led_states, index - 1, state);
    __update_leds();
}

void QwstPad::set_leds(bool state) {
    // Set all 4 LED bits to the same state
    for (uint8_t i = 0; i < NUM_LEDS; ++i) {
        __led_states = __change_bit(__led_states, i, state);
    }
    __update_leds();
}

uint8_t QwstPad::get_led_states() const {
    return __led_states;
}
void QwstPad::clear_leds() {
    // Clear all LED states
    __led_states = 0;
    __update_leds();
}

void QwstPad::__update_leds() {
    uint16_t output = 0;

    // Map internal 4-bit LED state to actual output bits in TCA9555
    for (uint8_t i = 0; i < NUM_LEDS; ++i) {
        // Invert logic: LED ON = bit LOW
        output = __change_bit(output, LED_MAPPING[i], !__get_bit(__led_states, i));
    }

    // Write 16-bit output register
    __reg_write_uint16(__i2c, __address, OUTPUT_PORT0, output);
}

bool QwstPad::__get_bit(uint16_t state, uint8_t index) {
    if (index > 15) {
        Serial.println(F("ERROR: __get_bit index out of range!"));
        return false;
    }
    //bool result = 
#ifdef MY_DEBUG
    if (__address = DEFAULT_ADDRESS || __address == ALT_ADDRESS_1) {
        if (result) {
            Serial.print(F("QwstPad::__get_bit(): param state = 0x"));
            Serial.print(state, HEX);
            Serial.print(F(", index = "));
            Serial.print(index);
            Serial.print(F(", result = "));
            Serial.println(result ? "true" : "false");
        }
    }
#endif
    //return (state >> index) & 0x01; // this results in an integer 0 or 1
    return (state & (1 << index)) != 0;  // this results in a bool
}

uint16_t QwstPad::__change_bit(uint16_t num, uint8_t bit_pos, bool state) const {
    // Set or clear bit at position `bit_pos` in 16-bit value
    return state ? (num | (1 << bit_pos)) : (num & ~(1 << bit_pos));
}

void QwstPad::__reg_write_uint16(TwoWire* i2c, uint8_t address, uint8_t reg, uint16_t value) {
#ifdef MY_DEBUG
    Serial.print(F("QwstPad::__reg_write_uint16(): reg: 0x"));
    Serial.print(reg, HEX);
    Serial.print(F(", value: 0b"));
    printBinary(value);
    Serial.print(F(" in HEX = 0x"));
    Serial.println(value, HEX);
#endif
    i2c->beginTransmission(address);
    i2c->write(reg);
    i2c->write(value & 0xFF);        // Low byte
    i2c->write((value >> 8) & 0xFF); // High byte
    i2c->endTransmission();
}

uint16_t QwstPad::__reg_read_uint16(TwoWire* i2c, uint8_t address, uint8_t reg) {
    // Read 16-bit value from TCA9555 register (little-endian)
    i2c->beginTransmission(address);
    i2c->write(reg);
    i2c->endTransmission(false); // Repeated start

    i2c->requestFrom(address, (uint8_t)2);
    uint8_t low = i2c->read();
    uint8_t high = i2c->read();
    //uint16_t retval = (static_cast<uint16_t>(high) << 8) | low;  // see alternate return below
    
#ifdef MY_DEBUG
    if (__address == DEFAULT_ADDRESS || __address == ALT_ADDRESS_1) {
        if (retval) {
            Serial.print(F("QwstPad::__reg_read_uint16(): high byte: 0b"));
            //printBinary(high);
            Serial.print(high, BIN);
            Serial.print(F(", in hex: 0x"));
            Serial.print(high, HEX);
            Serial.print(F(", low byte: 0b"));
            Serial.print(low, BIN);
            //printBinary(low);
            Serial.print(F(", in hex: 0x"));
            Serial.print(low, HEX);
            Serial.print(F(", return value: 0b"));
            printBinary(retval);
            Serial.println();
        }
    }
#endif
    //return retval;
    return (high << 8) | low; // alternate version from Copilot on 2025-08-15 at 16h50 UTC +1
}

void QwstPad::writeRegister16(uint8_t address, uint8_t reg, uint16_t value) {
    __i2c->beginTransmission(address);
    __i2c->write(reg);
    __i2c->write(value & 0xFF);        // Low byte
    __i2c->write((value >> 8) & 0xFF); // High byte
    __i2c->endTransmission();
}

uint16_t QwstPad::led_mask_for_button(Button button) const {
    static const std::map<Button, std::string> ID_TO_LABEL = {
        {BUTTON_UP, "U"},
        {BUTTON_DOWN, "D"},
        {BUTTON_LEFT, "L"},
        {BUTTON_RIGHT, "R"},
        {BUTTON_A, "A"},
        {BUTTON_B, "B"},
        {BUTTON_X, "X"},
        {BUTTON_Y, "Y"},
        {BUTTON_PLUS, "+"},
        {BUTTON_MINUS, "-"}
    };

    auto label_it = ID_TO_LABEL.find(button);
    if (label_it != ID_TO_LABEL.end()) {
        auto bit_it = BUTTON_MAPPING.find(label_it->second);
        if (bit_it != BUTTON_MAPPING.end()) {
            return __change_bit(0x0000, bit_it->second, true);
        }
    }
    return address_code(); // fallback: blink all
}