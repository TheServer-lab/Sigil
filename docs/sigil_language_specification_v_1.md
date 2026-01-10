# Sigil Language Specification — v1.0 (LOCKED)

**Status:** Locked / Stable  
**Purpose:** Prevent syntax drift and feature creep  
**Audience:** Humans first (kids, beginners, sysadmins)

---

## 1. Core Philosophy (Non‑Negotiable)

1. **Readability over power**  
   If a feature makes scripts harder to read, it is rejected.

2. **Words over symbols**  
   No cryptic punctuation-based syntax.

3. **No flags**  
   No `-f`, `/Y`, `--force`, etc. Behavior must be safe by default.

4. **One obvious way**  
   Each task has one clear, readable way to do it.

5. **Safe by default**  
   Destructive actions must be explicit or confirmed.

---

## 2. File Format

- Extension: `.sig`
- Encoding: UTF‑8
- One command per line

---

## 3. Comments

### Line comments
```
& This is a comment
```

- `&` as first non‑space character comments the entire line

### Block comments
```
/*
  Multi‑line comment
*/
```

---

## 4. Variables

### Declaration
```
let name = value
let name
```

- `let name` declares an empty variable

### Input sugar
```
let name = ask "Prompt"
```

### Read‑only
```
let -r version = 1
```

### Access
- `$name` or `${name}` inside strings
- `'name'` expands to variable value

---

## 5. Input / Output

### Output
```
say Hello world
```

### Input
```
ask name "Prompt"
ask = name
```

---

## 6. Control Flow

### Conditionals
```
if condition then command
```

Common conditions:
- `exists path`
- `last == 0`

### Loops

#### Inline
```
rpt 5 say Hello
rpt inf say Running
```

#### Block
```
rpt 3
  say Hello
endrpt
```

- `inf`, `forever`, `infinite` mean endless loop

---

## 7. Exit & Status

```
exit
exit 1
```

### Exit status variable
```
last
LAST
LAST_EXIT
```

- `0` = success
- non‑zero = failure

---

## 8. File & System Commands (Core Set)

### Files
```
cpy source dest
move source dest
dlt path
```

### Existence
```
exists path
```

### Wait / Pause
```
wait 1
pse
```

---

## 9. Script Context

### Script location
```
script.dir
script.file
```

### Arguments
```
arg 1
arg count
```

- Arguments are 1‑based

---

## 10. Shell Bridges

```
cp   # Command Prompt
ps   # PowerShell
sh   # POSIX shell
```

- No flags
- No implicit execution without user intent

---

## 11. Error Handling (Light)

```
try command
else say Failed
```

- No exceptions
- No stack traces

---

## 12. Forbidden Features (v1.x)

These **must never be added** in v1.x:

- Flags or switches
- Goto
- Symbol chaining (`&&`, `||`)
- Ternary expressions
- Implicit destructive behavior
- Complex expression grammar
- Hidden side effects

---

## 13. Versioning Rules

- **v1.x**: New commands only
- **v2.0**: Syntax changes allowed (if ever)
- Backwards compatibility is mandatory within v1.x

---

## 14. Final Rule

If a feature cannot be explained to a child in one sentence,
**it does not belong in Sigil v1.0.**

---

**Sigil v1.0 — Human‑Readable Scripting**

