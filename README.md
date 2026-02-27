# hwcc — Hardware Context Compiler

Transforms raw hardware documentation (datasheets, SVD files, reference manuals) into AI-optimized context files that any coding tool can consume.

## Quick Start

```bash
pip install hwcc

cd my-project
hwcc init --chip STM32F407
hwcc add docs/STM32F407.svd
hwcc status
```

## License

MIT
