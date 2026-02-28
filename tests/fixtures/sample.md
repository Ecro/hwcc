# STM32F407 SPI Configuration Notes

This document describes the SPI peripheral configuration for the STM32F407.

## Clock Configuration

The SPI clock is derived from APB1 (SPI2/SPI3) or APB2 (SPI1).

- APB1 max: 42 MHz
- APB2 max: 84 MHz

## Register Overview

| Register | Offset | Description |
|----------|--------|-------------|
| SPI_CR1  | 0x00   | Control register 1 |
| SPI_CR2  | 0x04   | Control register 2 |
| SPI_SR   | 0x08   | Status register |

## Code Example

```c
void spi_init(SPI_TypeDef *spi) {
    spi->CR1 = SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI;
    spi->CR1 |= SPI_CR1_SPE;
}
```

## Notes

Special characters: µs, °C, Ω, ±5%
