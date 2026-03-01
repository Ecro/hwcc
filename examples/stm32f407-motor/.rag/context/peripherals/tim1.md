# TIM1 — STM32F407

Advanced-timers

## Register Map

## TIM1

**Base Address:** `0x40010000`
**Description:** Advanced-timers

### Registers

| Register | Offset | Size | Access | Reset | Description |
|----------|--------|------|--------|-------|-------------|
| CR1 | 0x0000 | 32 | RW | 0x00000000 | control register 1 |
| CR2 | 0x0004 | 32 | RW | 0x00000000 | control register 2 |
| SMCR | 0x0008 | 32 | RW | 0x00000000 | slave mode control register |
| DIER | 0x000C | 32 | RW | 0x00000000 | DMA/Interrupt enable register |
| SR | 0x0010 | 32 | RW | 0x00000000 | status register |
| EGR | 0x0014 | 32 | WO | 0x00000000 | event generation register |
| CCMR1_Output | 0x0018 | 32 | RW | 0x00000000 | capture/compare mode register 1 (output mode) |
| CCMR1_Input | 0x0018 | 32 | RW | 0x00000000 | capture/compare mode register 1 (input mode) |
| CCMR2_Output | 0x001C | 32 | RW | 0x00000000 | capture/compare mode register 2 (output mode) |
| CCMR2_Input | 0x001C | 32 | RW | 0x00000000 | capture/compare mode register 2 (input mode) |
| CCER | 0x0020 | 32 | RW | 0x00000000 | capture/compare enable register |
| CNT | 0x0024 | 32 | RW | 0x00000000 | counter |
| PSC | 0x0028 | 32 | RW | 0x00000000 | prescaler |
| ARR | 0x002C | 32 | RW | 0x00000000 | auto-reload register |
| RCR | 0x0030 | 32 | RW | 0x00000000 | repetition counter register |
| CCR1 | 0x0034 | 32 | RW | 0x00000000 | capture/compare register 1 |
| CCR2 | 0x0038 | 32 | RW | 0x00000000 | capture/compare register 2 |
| CCR3 | 0x003C | 32 | RW | 0x00000000 | capture/compare register 3 |
| CCR4 | 0x0040 | 32 | RW | 0x00000000 | capture/compare register 4 |
| BDTR | 0x0044 | 32 | RW | 0x00000000 | break and dead-time register |
| DCR | 0x0048 | 32 | RW | 0x00000000 | DMA control register |
| DMAR | 0x004C | 32 | RW | 0x00000000 | DMA address for full transfer |

### CR1 Fields

| Field | Bits | Access | Reset | Description |
|-------|------|--------|-------|-------------|
| CKD | [9:8] | RW | 0x0 | Clock division |
| ARPE | [7] | RW | 0x0 | Auto-reload preload enable |
| CMS | [6:5] | RW | 0x0 | Center-aligned mode selection |
| DIR | [4] | RW | 0x0 | Direction |
| OPM | [3] | RW | 0x0 | One-pulse mode |
| URS | [2] | RW | 0x0 | Update request source |
| UDIS | [1] | RW | 0x0 | Update disable |
| CEN | [0] | RW | 0x0 | Counter enable |
