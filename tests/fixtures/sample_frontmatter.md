---
title: I2C Bus Configuration Guide
chip: STM32F407
doc_type: app_note
author: Engineering Team
version: "1.2"
---

# I2C Bus Configuration

This guide covers I2C peripheral setup on the STM32F407.

## Supported Modes

- Standard mode (100 kHz)
- Fast mode (400 kHz)
- Fast mode plus (1 MHz)

## Pin Configuration

```c
// I2C1: PB6 (SCL), PB7 (SDA)
// I2C2: PB10 (SCL), PB11 (SDA)
```
