/*
* qwstPad.h
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
#ifndef QWSTPAD_H
#define QWSTPAD_H

#pragma once

#include <Arduino.h>
#include <Wire.h>
#include <unordered_map>
#include <map>
#include <vector>
#include <stdexcept>  // for std::invalid_argument
#include <algorithm>  // for std::find
#include <string>
#include <cstdint>
#include <utility>   // for std::pair
#include <cstdarg>   // for va_list, va_start, va_end
#include <iostream>  // for std::cout, std::cerr
#include "Stream.h"
#include "Print.h"

const char __version__[] = "0.0.1";

#ifdef MY_DEBUG
#undef MY_DEBUG 
#endif 

/*
#ifndef MY_DEBUG
#define MY_DEBUG 
#endif 
*/

#ifndef DEFAULT_I2C_PORT
#define DEFAULT_I2C_PORT &Wire
#endif

#ifndef SECONDARY_I2C_PORT
#define SECONDARY_I2C_PORT &Wire1
#endif

// Constants
const uint8_t MAX_PADS = 4; // Maximum number of pads supported
const uint8_t NUM_LEDS = 4;
const uint8_t NUM_BUTTONS = 10;

const uint8_t DEFAULT_ADDRESS = 0x21;
const uint8_t ALT_ADDRESS_1 = 0x23;
const uint8_t ALT_ADDRESS_2 = 0x25;
const uint8_t ALT_ADDRESS_3 = 0x27;

const uint8_t ADDRESSES[] = {DEFAULT_ADDRESS, ALT_ADDRESS_1, ALT_ADDRESS_2, ALT_ADDRESS_3};

// Register constants
const uint8_t INPUT_PORT0 = 0x00;
const uint8_t INPUT_PORT1 = 0x01;
const uint8_t OUTPUT_PORT0 = 0x02;
const uint8_t OUTPUT_PORT1 = 0x03;
const uint8_t POLARITY_PORT0 = 0x04;
const uint8_t POLARITY_PORT1 = 0x05;
const uint8_t CONFIGURATION_PORT0 = 0x06;
const uint8_t CONFIGURATION_PORT1 = 0x07;

// Button definitions
enum Button {
    BUTTON_NONE    = -1,
    BUTTON_UP      = 1,
    BUTTON_LEFT    = 2,
    BUTTON_RIGHT   = 3,
    BUTTON_DOWN    = 4,
    BUTTON_MINUS   = 5,
    BUTTON_PLUS    = 11,
    BUTTON_B       = 12,
    BUTTON_Y       = 13,
    BUTTON_A       = 14,
    BUTTON_X       = 15
};

//#define TCA9555_ADDRESS 0x21  // Or 0x23, 0x25, 0x27 depending on your hardware

#define CONFIG_PORT0 0x06
#define CONFIG_PORT1 0x07
#define POLARITY_PORT0 0x04
#define POLARITY_PORT1 0x05
#define OUTPUT_PORT0 0x02
#define OUTPUT_PORT1 0x03


extern const std::unordered_map<std::string, uint8_t> BUTTON_MAPPING;
extern const std::vector<uint8_t> LED_MAPPING;

enum ButtonEventType { PRESSED, RELEASED };

struct ButtonEvent {
    std::string key;
    ButtonEventType type;
};

enum LogicType {UNKNOWN = -1, ACTIVE_HIGH = 0, ACTIVE_LOW = 1};

struct padConfig {
    int padID;
    LogicType logic;
    std::map<std::string, int> buttonPins;
};

// If you want each QwstPad instance to know its config, you could add:
extern padConfig* __config;  // ✅ Declaration only


struct ButtonDescriptor {
    std::string label;
    uint8_t logicalValue;
    uint8_t pinIndex;
};


class QwstPad {
public:
    //QwstPad(); // default constructor
    explicit QwstPad(uint8_t address);      // Uses default Wire
    QwstPad(TwoWire* i2c_port, uint8_t address, bool show_address); // Custom Wire port
    void init(TwoWire* i2c_port, uint8_t address, bool show_address);
    void deinit();
    void begin();
    bool IsInitialized() const; // Check if the pad is initialized
    bool isValidAddress(uint8_t addr);
    void clear_button_states();
    bool isConnected();
    uint8_t getAddress() const;
    uint8_t getpadIDFromAddress(uint8_t address);
    uint16_t address_code() const;
    padConfig* getConfig();
    std::map<std::string, bool> read_buttons();
    std::map<std::string, bool> read_buttons2();
    void pr_PadID() const;
    void printAllPadConfigs() const;
    uint16_t getButtonBitfield(bool show, bool fancy);
    int8_t getFirstPressedButtonBitIndex();
    std::string getFirstPressedButtonName();
    int8_t getLogicType();
    int8_t setLogicType(LogicType type);
    std::vector<ButtonEvent> pollEvents();
    uintptr_t debugConfigPointer() const;
    bool debugPrintStates() const;
    void update();
    bool readRawPin(int index);

    const std::map<std::string, bool>& getCurrentStates() const {
      return __button_states;
    }

    const std::map<std::string, bool>& getPreviousStates() const {
      return __last_button_states;
    }

    bool isButtonPressed(const std::string& key);
    bool wasPressed(const std::string& key) const;
    bool wasReleased(const std::string& key) const;
    bool buttonChanged(const std::string& key);
    bool getButtonState(const std::string& key) const;
    void set_led(uint8_t index, bool state);
    void set_leds(bool state);
    void clear_leds();
    uint8_t get_led_states() const;
    uint16_t led_mask_for_button(Button button) const;

private:
    TwoWire* __i2c;
    uint8_t __address;
    uint8_t __led_states;
    uint8_t __padID;

    std::map<std::string, bool> __button_states;
    std::map<std::string, bool> __last_button_states;
    ButtonDescriptor makeButtonDescriptor(const std::string& label, uint8_t pinIdx);
    std::vector<ButtonDescriptor> makeButtons(const std::vector<std::pair<std::string, uint8_t>>& labelBitIndexPairs);
    void serialPrintf(const char* format, ...) const;
    void printBinary(uint16_t num, bool fancy) const;
    void pr_spc(uint8_t cnt) const;
    void pr_dashBar() const;
    void __update_leds();
    bool __get_bit(uint16_t state, uint8_t index);
    uint16_t __change_bit(uint16_t num, uint8_t bit_pos, bool state) const;
    void __reg_write_uint16(TwoWire* i2c, uint8_t address, uint8_t reg, uint16_t value);
    uint16_t __reg_read_uint16(TwoWire* i2c, uint8_t address, uint8_t reg);
    void writeRegister16(uint8_t address, uint8_t reg, uint16_t value);
    void setupTCA9555();
};

#endif // QWSTPAD_H
