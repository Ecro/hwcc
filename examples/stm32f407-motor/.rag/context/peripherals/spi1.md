# SPI1 — STM32F407

Serial peripheral interface

## Register Map

## SPI1

**Base Address:** `0x40013000`
**Description:** Serial peripheral interface

### Registers

| Register | Offset | Size | Access | Reset | Description |
|----------|--------|------|--------|-------|-------------|
| CR1 | 0x0000 | 32 | RW | 0x00000000 | control register 1 |
| CR2 | 0x0004 | 32 | RW | 0x00000000 | control register 2 |
| SR | 0x0008 | 32 | — | 0x00000002 | status register |
| DR | 0x000C | 32 | RW | 0x00000000 | data register |
| CRCPR | 0x0010 | 32 | RW | 0x00000007 | CRC polynomial register |
| RXCRCR | 0x0014 | 32 | RO | 0x00000000 | RX CRC register |
| TXCRCR | 0x0018 | 32 | RO | 0x00000000 | TX CRC register |
| I2SCFGR | 0x001C | 32 | RW | 0x00000000 | I2S configuration register |
| I2SPR | 0x0020 | 32 | RW | 0x0000000A | I2S prescaler register |

### CR1 Fields

| Field | Bits | Access | Reset | Description |
|-------|------|--------|-------|-------------|
| BIDIMODE | [15] | RW | 0x0 | Bidirectional data mode enable |
| BIDIOE | [14] | RW | 0x0 | Output enable in bidirectional mode |
| CRCEN | [13] | RW | 0x0 | Hardware CRC calculation enable |
| CRCNEXT | [12] | RW | 0x0 | CRC transfer next |
| DFF | [11] | RW | 0x0 | Data frame format |
| RXONLY | [10] | RW | 0x0 | Receive only |
| SSM | [9] | RW | 0x0 | Software slave management |
| SSI | [8] | RW | 0x0 | Internal slave select |
| LSBFIRST | [7] | RW | 0x0 | Frame format |
| SPE | [6] | RW | 0x0 | SPI enable |
| BR | [5:3] | RW | 0x0 | Baud rate control |
| MSTR | [2] | RW | 0x0 | Master selection |
| CPOL | [1] | RW | 0x0 | Clock polarity |
| CPHA | [0] | RW | 0x0 | Clock phase |

### CR2 Fields

| Field | Bits | Access | Reset | Description |
|-------|------|--------|-------|-------------|
| TXEIE | [7] | RW | 0x0 | Tx buffer empty interrupt enable |
| RXNEIE | [6] | RW | 0x0 | RX buffer not empty interrupt enable |
| ERRIE | [5] | RW | 0x0 | Error interrupt enable |
| FRF | [4] | RW | 0x0 | Frame format |
| SSOE | [2] | RW | 0x0 | SS output enable |
| TXDMAEN | [1] | RW | 0x0 | Tx buffer DMA enable |
| RXDMAEN | [0] | RW | 0x0 | Rx buffer DMA enable |

### SR Fields

| Field | Bits | Access | Reset | Description |
|-------|------|--------|-------|-------------|
| TIFRFE | [8] | RO | 0x0 | TI frame format error |
| BSY | [7] | RO | 0x0 | Busy flag |
| OVR | [6] | RO | 0x0 | Overrun flag |
| MODF | [5] | RO | 0x0 | Mode fault |
| CRCERR | [4] | RW | 0x0 | CRC error flag |
| UDR | [3] | RO | 0x0 | Underrun flag |
| CHSIDE | [2] | RO | 0x0 | Channel side |
| TXE | [1] | RO | 0x1 | Transmit buffer empty |
| RXNE | [0] | RO | 0x0 | Receive buffer not empty |

### DR Fields

| Field | Bits | Access | Reset | Description |
|-------|------|--------|-------|-------------|
| DR | [15:0] | RW | 0x0000 | Data register |
