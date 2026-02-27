# Python Coding Standards

## Type Hints
- All public functions must have parameter and return type annotations
- Use `X | None` union syntax (not `Optional[X]`)
- Use `list[str]`, `dict[str, int]` lowercase generics (not `List`, `Dict`)
- Never use `Any` unless absolutely necessary and documented why
- Use `TypeAlias` for complex type definitions

## Data Structures
- Use `@dataclass` for data containers (HwccConfig, Manifest, DocumentEntry)
- Use `@dataclass(frozen=True)` for immutable value objects (ChunkMetadata)
- Field defaults: `field(default_factory=list)`
- Use `pydantic.BaseModel` only if validation needed at system boundaries

## Path Handling
- Always use `pathlib.Path`, never `os.path` string manipulation
- `Path.resolve()` for absolute paths
- `Path.relative_to()` for relative paths
- Never construct paths with string concatenation

## Error Handling
- Never bare `except:` — always `except SpecificError`
- Custom exception hierarchy: `HwccError` base, then `ParseError`, `ConfigError`, `EmbeddingError`, `StoreError`
- Use `raise ... from e` to preserve exception chains
- Log errors before raising: `logger.error("Failed to parse %s: %s", path, e)`

## File I/O
- Always use context managers: `with open(path) as f:`
- Specify encoding explicitly: `open(path, encoding="utf-8")`
- Use `Path.read_text()` / `Path.write_text()` for simple operations
- Use `tempfile.TemporaryDirectory()` for temp files in tests

## Logging
- Use `logging` module, never `print()` for diagnostics
- Logger per module: `logger = logging.getLogger(__name__)`
- Levels: `error` for failures, `warning` for unexpected-but-handled, `info` for state changes, `debug` for detailed tracing
- Use Rich handler for CLI output (`rich.logging.RichHandler`)

## Module Structure
- `__all__` in every `__init__.py` to define public API
- Imports: stdlib first, then third-party, then local (ruff enforces via `isort`)
- Abstract base classes in `base.py` within each package
- One class per file for major abstractions

## CLI Patterns (Typer)
- Type-annotated CLI parameters: `Annotated[str, typer.Argument(help="...")]`
- Rich console for formatted output
- `typer.echo()` for simple output, `console.print()` for Rich formatted
- `raise typer.Exit(code=1)` for error exits, never `sys.exit()`
- Callback-based app structure for subcommands

## Testing Patterns (pytest)
- Test file naming: `test_<module>.py`
- Test function naming: `test_<what>_<scenario>_<expected>`
- Use `conftest.py` for shared fixtures
- Use `tmp_path` for temporary file operations
- Use `monkeypatch` for environment variable mocking
- Use `pytest.raises(SpecificError)` for exception testing

## String Formatting
- f-strings preferred: `f"Processing {path.name}"`
- `textwrap.dedent()` for multi-line strings in tests
- Raw strings for regex: `r"\d+\.\d+"`
