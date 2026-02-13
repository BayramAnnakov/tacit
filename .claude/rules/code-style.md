---
description: Python and Swift coding conventions
---

## Python

- Add imports at the top of the file, avoid duplicate imports scattered through the file
- Use `async`/`await` for all database operations (aiosqlite requires it)
- Use `@tool(name=..., description=..., input_schema={...})` decorator for MCP tools
- Use type hints in function signatures: `async def list_rules(category: str | None = None) -> list[dict]`
- Use snake_case for variables, functions, and file names
- Use `Path` from pathlib for file system operations
- Use `httpx.AsyncClient` for HTTP requests (not `requests`)
- Prefer f-strings over `.format()` or `%` formatting

## Swift

- Use `@Observable` for view models (not `ObservableObject`)
- Use `@State` for view-local state, `@Bindable` for bindable view model properties
- Use camelCase for variables, functions, and properties
- Use PascalCase for types, protocols, and enums
- Organize SwiftUI views with computed body properties and extracted subviews
