# 🔮 Sigil Programming Guide

Welcome to Sigil - a friendly, powerful shell and scripting language that makes working with your computer fun and intuitive!

## What is Sigil?

Sigil is an alternative to traditional shells like Bash or PowerShell, designed to be:
- **Easy to learn** - clear command names and helpful error messages
- **Forgiving** - built-in undo/redo for file operations
- **Fun** - playful features and friendly terminology
- **Powerful** - full scripting capabilities with variables, loops, and plugins

## Getting Started

### Running Sigil

**Interactive Mode (REPL):**
```bash
python sigil.py
```

**Run a Script:**
```bash
python sigil.py myscript.sig
```

### Your First Commands (Glyphs)

In Sigil, commands are called **glyphs**. Here are some basics:

```
sigil> say Hello, World!
Hello, World!

sigil> pwd
C:\Users\YourName

sigil> help
Available glyphs:
  add, alia, arg, ask, bored, cd, clo, cmd, ...
```

## Comments

Sigil supports multiple comment styles:

```
& This is a comment (kid-friendly!)
# This is also a comment
// C-style comment
/* Block comment
   spanning multiple lines */
```

## File Operations

### Creating Files and Directories

```
mk dir MyFolder              & Create a directory
mk file hello.txt Hello!     & Create a file with content
```

### Copying, Moving, Deleting

```
cpy hello.txt backup.txt     & Copy a file
move file old.txt new.txt    & Move/rename a file
renm old.txt new.txt         & Shortcut for rename
dlt unwanted.txt             & Delete (can undo!)
```

### Navigating

```
cd MyFolder                  & Change directory
pwd                          & Print working directory
dirlook                      & List directory contents
```

### Viewing and Editing

```
edt myfile.txt               & Edit in default editor
opn document.pdf             & Open with default app
ex                           & Open Explorer (Windows)
```

### Undo/Redo

One of Sigil's superpowers - undo file operations!

```
dlt important.txt
& Oops! I didn't mean to delete that!
undo
& Phew! File is back.

redo
& Actually, I did want to delete it.
```

## Variables

### Creating Variables

```
let name = Alice
let age = 25
let price = 19.99
let message = "Hello, world!"
```

### Using Variables

Multiple ways to reference variables:

```
let name = Bob

say name                     & Prints: Bob
say $name                    & Prints: Bob
say ${name}                  & Prints: Bob
say 'name'                   & Prints: Bob (single-quote shorthand)
say "Hello, $name!"          & Prints: Hello, Bob!
```

### Special Variable Features

```
let -r PI = 3.14159          & Readonly variable
export PATH                  & Export to OS environment

var                          & List all variables
unset oldvar                 & Remove a variable
```

### Interactive Input

```
ask username "Enter your name: "
say "Hello, $username!"

& Or use shorthand
let name = ask "Your name: "
```

## Aliases

Create shortcuts for common commands:

```
alia ll dirlook
alia hello say "Hello, World!"
alia gs cd C:\Games\Steam

unalia hello                 & Remove an alias
alia                         & List all aliases
```

## Arithmetic

Sigil has built-in math commands:

```
add 10 20 30                 & Prints: 60
sub 100 25                   & Prints: 75
mul 5 7 2                    & Prints: 70
div 100 4                    & Prints: 25

& Works with variables too
let x = 10
let y = 5
add x y                      & Prints: 15
```

## Conditional Execution

### Basic If Statements

```
if exists myfile.txt then say "File exists!"

let age = 18
if age >= 18 then say "Adult"

let name = Alice
if name == "Alice" then say "Hello, Alice!"
```

### Comparison Operators

- `==` - equal to
- `!=` - not equal to
- `>` - greater than
- `<` - less than
- `>=` - greater than or equal
- `<=` - less than or equal

## Loops

### Simple Loops

```
rpt 5 say "Hello!"           & Print 5 times

let x = 0
rpt 10 let x = add x 1       & Count to 10
```

### Block Loops

```
rpt 3
  say "Starting iteration"
  wait 1
  say "Done!"
endrpt
```

### Infinite Loops

```
rpt inf
  say "Press Ctrl+C to stop!"
  wait 1
endrpt
```

## Writing Scripts

### Script Structure

Create a file `greet.sig`:

```
& greet.sig - A friendly greeting script

ask name "What's your name? "

if name == "" then let name = "Friend"

say "Hello, $name!"
say "Welcome to Sigil!"

let time = ask "How's your day been? "
say "Glad to hear it was $time!"
```

Run it:
```
sigil> run greet.sig
```

### Script Arguments

Scripts can accept arguments:

```
& backup.sig - Backup a file

if arg count < 1 then say "Usage: backup.sig <filename>" exit 1

let filename = arg 1
let backup_name = "${filename}.bak"

cpy $filename $backup_name
say "Backed up $filename to $backup_name"
```

Run with arguments:
```
sigil> run backup.sig important.txt
```

### Script Variables

Inside scripts, you have access to:

```
script.file                  & Full path to the script
script.dir                   & Directory containing the script

& Use them:
let config = "${script.dir}/config.txt"
```

## Shell Integration

Sigil can run commands in other shells:

### PowerShell

```
ps Get-Process               & Run PowerShell command
ps                           & Open interactive PowerShell
```

### Command Prompt

```
cmd dir                      & Run cmd command
cp dir                       & Shortcut for cmd
cmd                          & Open interactive cmd
```

### POSIX Shell (bash/sh)

```
sh ls -la                    & Run shell command
sh                           & Open interactive shell
```

## Useful Utilities

### Wait/Sleep

```
wait 2                       & Wait 2 seconds
wait 0.5                     & Wait half a second
```

### File Information

```
siz largefile.zip            & Show file size in bytes
exists myfile.txt            & Prints "yes" or "no"
```

### Process Management

```
task                         & List running processes
kill task notepad.exe        & Force kill a process
clo task notepad.exe         & Gracefully close a process
```

### Opening Things

```
opnlnk https://google.com    & Open URL in browser
opn document.pdf             & Open file with default app
opnapp calculator            & Launch an application
```

### Fun Commands

```
bored                        & Display random movie quotes
& Press any key to stop!
```

## Profiles

Manage different configurations:

```
prof                         & List all profiles
prof show                    & Show current profile
prof new work                & Create new profile
prof work                    & Switch to work profile
prof del old_profile         & Delete a profile
```

Each profile has its own:
- Aliases
- Variables
- Settings

Stored in `C:\Sigil\.sigilrc` files.

## Configuration Management

```
svrc                         & Save current config
rrc                          & Reload config from disk
```

Your `.sigilrc` file contains:
- All your aliases
- All your variables
- Exported variables
- Readonly variables

## Advanced Features

### Pause for Input

```
pse "About to delete files. Ready?"
& Waits for keypress before continuing

pse
& Just waits without a message
```

### Script Formatting

```
fmt myscript.sig             & Auto-format (trim whitespace)
schk myscript.sig            & Check syntax
```

### Including Other Scripts

```
inc utils.sig                & Run another script inline
run helper.sig               & Run script in its own context
```

## Plugins

Extend Sigil with plugins (`.sigin` files):

```
pin                          & List installed plugins
pin myplugin.sigin           & Install a plugin
prv myplugin                 & Remove a plugin
```

Plugins can add new glyphs and functionality!

## Complete Example: Task Manager

Here's a complete script showing many features:

```
& task_manager.sig - Simple task list manager

let tasklist = "${script.dir}/tasks.txt"

& Check if task file exists
if exists $tasklist then say "Loading tasks..." else mk file $tasklist ""

say "=== Task Manager ==="
say "1. Add task"
say "2. View tasks"
say "3. Clear tasks"
say ""

ask choice "Choose option: "

if choice == "1" then
  ask task "Enter task: "
  let content = ask "Task details: "
  say "Task added: $task"
endrpt

if choice == "2" then
  say "Viewing tasks..."
  opn $tasklist
endrpt

if choice == "3" then
  ask confirm "Delete all tasks? (yes/no): "
  if confirm == "yes" then
    dlt $tasklist
    mk file $tasklist ""
    say "Tasks cleared!"
  endrpt
endrpt

say "Goodbye!"
```

## Tips & Tricks

### 1. Use Variables for Paths

```
let projects = C:\Users\Me\Projects
cd $projects
```

### 2. Chain Commands Safely

```
if exists backup.zip then dlt backup.zip
mk dir temp_backup
cpy important.txt temp_backup/
```

### 3. Script Templates

Start scripts with:
```
& script_name.sig - Description
& Author: Your Name
& Date: 2026-01-11

& Check arguments
if arg count < 1 then
  say "Usage: script_name.sig <arg>"
  exit 1
endrpt
```

### 4. Error Handling

Use the `last` variable to check command results:
```
cpy file.txt backup.txt
if last == 0 then say "Success!" else say "Failed!"
```

### 5. Directory Bookmarks

```
& In your .sigilrc
alia proj cd C:\Projects
alia docs cd C:\Users\Me\Documents
alia dl cd C:\Users\Me\Downloads
```

## Common Patterns

### Backup Before Editing

```
let file = important.txt
cpy $file "${file}.bak"
edt $file
```

### Batch Processing

```
let count = 5
rpt $count
  let filename = "file${count}.txt"
  mk file $filename "Content"
  let count = sub count 1
endrpt
```

### Interactive Menu

```
say "Choose an option:"
say "1. Option A"
say "2. Option B"
ask choice "> "

if choice == "1" then say "You picked A!"
if choice == "2" then say "You picked B!"
```

## Getting Help

```
help                         & List all glyphs
help <glyph>                 & Get help on specific glyph
```

## Summary

Sigil gives you:
- ✨ **Simple syntax** - easy to read and write
- 🔄 **Undo/redo** - safe file operations
- 📦 **Variables & aliases** - customize your workflow
- 🔁 **Loops & conditions** - full scripting power
- 🧩 **Plugins** - extend functionality
- 🎯 **Cross-platform** - works on Windows, Mac, Linux

Start experimenting and have fun! Remember: you can always `undo` if something goes wrong.

Happy scripting! 🔮
