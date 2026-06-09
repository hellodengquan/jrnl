<!--
Copyright © 2012-2023 jrnl contributors
License: https://www.gnu.org/licenses/gpl-3.0.html
-->

# Formats

`jrnl` supports a variety of alternate formats. These can be used to display your
journal in a different manner than the `jrnl` default, and can even be used to pipe data
from your journal for use in another program to create reports, or do whatever you want
with your `jrnl` data.

Any of these formats can be used with a search (e.g. `jrnl -contains "lorem ipsum"
--format json`) to display the results of that search in the given format, or can be
used alone (e.g. `jrnl --format json`) to display all entries from the selected journal.

This page shows examples of all the built-in formats, but since `jrnl` supports adding
more formats through plugins, you may have more available on your system. Please see
`jrnl --help` for a list of which formats are available on your system.

Any of these formats can be used interchangeably, and are only grouped into "display",
"data", and "report" formats below for convenience.

## Display Formats
These formats are mainly intended for displaying your journal in the terminal. Even so,
they can still be used in the same way as any other format (like written to a file, if
you choose).

### Pretty
``` sh
jrnl --format pretty
# or
jrnl -1 # any search
```

This is the default format in `jrnl`. If no `--format` is given, `pretty` will be used.

It displays the timestamp of each entry formatted to by the user config followed by the
title on the same line. Then the body of the entry is shown below.

This format is configurable through these values from your config file (see
[Advanced Usage](./advanced.md) for more details):

- `colors`
    - `body`
    - `date`
    - `tags`
    - `title`
- `indent_character`
- `linewrap`
- `timeformat`

**Example output**:
``` sh
2020-06-28 18:22 This is the first sample entry
| This is the sample body text of the first sample entry.

2020-07-01 20:00 This is the second sample entry
| This is the sample body text of the second sample entry, but
| this one has a @tag.

2020-07-02 09:00 This is the third sample entry
| This is the sample body text of the third sample entry.
```

### Short

``` sh
jrnl --format short
# or
jrnl --short
```

This will shorten entries to display only the date and title. It is essentially the
`pretty` format but without the body of each entry. This can be useful if you have long
journal entries and only want to see a list of entries that match your search.

**Example output**:
``` sh
2020-06-28 18:22 This is the first sample entry
2020-07-01 20:00 This is the second sample entry
2020-07-02 09:00 This is the third sample entry
```

### Fancy (or Boxed)
``` sh
jrnl --format fancy
# or
jrnl --format boxed
```

This format outlines each entry with a border. This makes it much easier to tell where
each entry starts and ends. It's an example of how free-form the formats can be, and also
just looks kinda ~*~fancy~*~, if you're into that kind of thing.

**Example output**:
``` sh
┎──────────────────────────────────────────────────────────────────────╮2020-06-28 18:22
┃ This is the first sample entry                                       ╘═══════════════╕
┠╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤
┃ This is the sample body text of the first sample entry.                              │
┖──────────────────────────────────────────────────────────────────────────────────────┘
┎──────────────────────────────────────────────────────────────────────╮2020-07-01 20:00
┃ This is the second sample entry                                      ╘═══════════════╕
┠╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤
┃ This is the sample body text of the second sample entry, but this one has a @tag.    │
┖──────────────────────────────────────────────────────────────────────────────────────┘
┎──────────────────────────────────────────────────────────────────────╮2020-07-02 09:00
┃ This is the third sample entry                                       ╘═══════════════╕
┠╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤
┃ This is the sample body text of the third sample entry.                              │
┖──────────────────────────────────────────────────────────────────────────────────────┘
```

## Data Formats
These formats are mainly intended for piping or exporting your journal to other
programs. Even so, they can still be used in the same way as any other format (like
written to a file, or displayed in your terminal, if you want).

!!! note
You may see boxed messages like "2 entries found" when using these formats, but
those messages are written to `stderr` instead of `stdout`, and won't be piped when
using the `|` operator.

### JSON

``` sh
jrnl --format json
```

JSON is a very handy format used by many programs and has support in nearly every
programming language. There are many things you could do with JSON data. Maybe you could
use `jq` ([project page](https://github.com/stedolan/jq)) to filter through the fields in your journal.
Like this:

``` sh
$ j -3 --format json | jq '.entries[].date'                                                                                                                            jrnl-GFqVlfgP-py3.8 
"2020-06-28"
"2020-07-01"
"2020-07-02"
```

Or why not create a [beautiful timeline](http://timeline.knightlab.com/) of your journal?

**Example output**:
``` json
{
  "tags": {
    "@tag": 1
  },
  "entries": [
    {
      "title": "This is the first sample entry",
      "body": "This is the sample body text of the first sample entry.",
      "date": "2020-06-28",
      "time": "18:22",
      "tags": [],
      "starred": false
    },
    {
      "title": "This is the second sample entry",
      "body": "This is the sample body text of the second sample entry, but this one has a @tag.",
      "date": "2020-07-01",
      "time": "20:00",
      "tags": [
        "@tag"
      ],
      "starred": false
    },
    {
      "title": "This is the third sample entry",
      "body": "This is the sample body text of the third sample entry.",
      "date": "2020-07-02",
      "time": "09:00",
      "tags": [],
      "starred": false
    }
  ]
}
```

### Markdown

``` sh
jrnl --format markdown
# or
jrnl --format md
```

Markdown is a simple markup language that is human readable and can be used to be
rendered to other formats (html, pdf). `jrnl`'s
[README](https://github.com/jrnl-org/jrnl/blob/develop/README.md) for example is
formatted in markdown, then Github adds some formatting to make it look nice.

The markdown format groups entries by date (first by year, then by month), and adds
header markings as needed (e.g. `#`, `##`, etc). If you already have markdown header
markings in your journal, they will be incremented as necessary to make them fit under
these new headers (i.e. `#` will become `##`).

This format can be very useful, for example, to export a journal to a program that
converts markdown to html to make a website or a blog from your journal.

**Example output**:
``` markdown
# 2020

## June

### 2020-06-28 18:22 This is the first sample entry

This is the sample body text of the first sample entry.

## July

### 2020-07-01 20:00 This is the second sample entry

This is the sample body text of the second sample entry, but this one has a @tag.

### 2020-07-02 09:00 This is the third sample entry

This is the sample body text of the third sample entry.
```

### Plain Text

``` sh
jrnl --format text
# or
jrnl --format txt
```

This outputs your journal in the same plain-text format that `jrnl` uses to store your
journal on disk. This format is particularly useful for importing and exporting journals
within `jrnl`.

You can use it, for example, to move entries from one journal to another, or to create a
new journal with search results from another journal.

**Example output**:
``` sh
[2020-06-28 18:22] This is the first sample entry
This is the sample body text of the first sample entry.

[2020-07-01 20:00] This is the second sample entry
This is the sample body text of the second sample entry, but this one has a @tag.

[2020-07-02 09:00] This is the third sample entry
This is the sample body text of the third sample entry.
```

### XML
``` sh
jrnl --format xml
```

This outputs your journal into XML format. XML is a commonly used data format and is
supported by many programs and programming languages.

**Example output**:
``` xml
<?xml version="1.0" ?>
<journal>
        <entries>
                <entry date="2020-06-28T18:22:00" starred="">This is the first sample entry This is the sample body text of the first sample entry.</entry>
                <entry date="2020-07-01T20:00:00" starred="">
                        <tag name="@tag"/>
                        This is the second sample entry This is the sample body text of the second sample entry, but this one has a @tag.
                </entry>
                <entry date="2020-07-02T09:00:00" starred="">*This is the third sample entry, and is starred This is the sample body text of the third sample entry.</entry>
        </entries>
        <tags>
                <tag name="@tag">1</tag>
        </tags>
</journal>
```

### YAML
``` sh
jrnl --format yaml --file 'my_directory/'
```

This outputs your journal into YAML format. YAML is a commonly used data format and is
supported by many programs and programming languages. [Exporting to directories](#exporting-to-directories) is the
only supported YAML export option and each entry will be written to a separate file.

**Example file**:
``` yaml
title: This is the second sample entry
date: 2020-07-01 20:00
starred: False
tags: tag

This is the sample body text of the second sample entry, but this one has a @tag.
```

## Template (Custom Export Format)

``` sh
jrnl --format template
# or
jrnl --format tpl
```

The `template` format allows you to fully customize the export output using reusable
template files. With templates, you can organize your journal entries by date, tags,
and body snippets to create reports, web pages, custom data formats, or anything you
can imagine.

### Quick Start

``` sh
# Use the built-in default template
jrnl --format template

# Use a specific template with --export-template
jrnl --format template --export-template my_report.template

# Write output to a file
jrnl --format template --export-template default_html.template --file journal.html
```

### Specifying Templates

You can specify a custom template in two ways:

1. **Command line**: Use `--export-template PATH`
    ```sh
    jrnl --format template --export-template /path/to/my_template.template
    ```

2. **Configuration file**: Add to your journal config in `~/.config/jrnl/jrnl.yaml`:
    ```yaml
    default:
      export_template: /path/to/my_template.template
    ```

Template paths can be:
- Absolute paths (e.g., `/home/user/templates/report.template`)
- Relative paths (e.g., `./my_template.template`)
- File names inside the jrnl templates directory
  (e.g., `$XDG_DATA_HOME/jrnl/templates/default_html.template`)

### Built-in Templates

jrnl ships with several ready-to-use templates:

| Template File          | Extension | Description                                             |
|------------------------|-----------|---------------------------------------------------------|
| `default_text.template`  | `.txt`   | Plain text format with dates, titles, tags, and body    |
| `default_markdown.template` | `.md`  | Markdown with table of contents and tag statistics     |
| `default_html.template`   | `.html`  | Styled HTML report with navigation and stats cards     |
| `summary.template`       | `.txt`   | Quick summary with title, date, tags, and body preview |
| `custom_json.template`   | `.md` (json) | Custom JSON structure with entries and tag summary  |

Example using built-in templates:
```sh
# Generate HTML report
jrnl --format template --export-template default_html.template --file report.html

# Get quick summary
jrnl --format template --export-template summary.template

# Export as custom JSON
jrnl --format template --export-template custom_json.template --file backup.json
```

### Template Syntax

Templates use a lightweight syntax similar to Jinja2. Here are all the supported features:

#### Variables: `{{ variable }}`

Output the value of a variable or expression.

```jinja
{{ entry.title }}
{{ entry.date }}
{{ journal.entry_count }}
```

#### Attributes: `{{ object.attribute }}`

Access nested attributes with dot notation.

```jinja
{{ entry.title }}
{{ entry.date.year }}
{{ journal.name }}
```

#### Slicing/Indexing: `{{ variable[start:stop] }}`

Extract substrings or list elements using Python-style slicing.

```jinja
{{ entry.body[:100] }}       {# First 100 characters of body #}
{{ entry.tags[0] }}          {# First tag #}
{{ entry.body[20:50] }}      {# Characters 20-49 #}
```

#### Filters: `{{ variable | filter_name:"args" }}`

Transform values using pipe (`|`) filters. Multiple filters can be chained.

```jinja
{{ entry.date | date:"%Y-%m-%d" }}
{{ entry.tags | join:", " }}
{{ entry.body | truncate:150,"..." }}
{{ entry.title | upper | strip }}
```

#### Loops: `{% for var in iterable %} ... {% endfor %}`

Iterate over lists. Special `loop` variables are available inside loops.

```jinja
{% for entry in entries %}
  {{ loop.index }}. {{ entry.title }}
{% endfor %}
```

#### Conditionals: `{% if condition %} ... {% else %} ... {% endif %}`

Branch logic with optional `{% else %}` block. Supports `not` for negation.

```jinja
{% if entry.starred %}⭐{% endif %}

{% if entry.tags %}
  Tags: {{ entry.tags | join:", " }}
{% else %}
  No tags
{% endif %}

{% if not loop.last %}---{% endif %}
```

#### YAML Front Matter

Templates can optionally start with YAML front matter (delimited by `---`) to set
metadata:

```jinja
---
extension: html
name: My Custom Report
description: Beautiful HTML export of my journal
---
<!DOCTYPE html>
<html>...
```

Supported front matter fields:
- `extension`: Output file extension (e.g., `md`, `html`, `txt`, `json`)
- `name`: Human-readable template name
- `description`: What this template does

### Available Variables

#### Top-level Variables

| Variable            | Type   | Description                                      |
|---------------------|--------|--------------------------------------------------|
| `entries`           | list   | All matching journal entries                     |
| `journal`           | dict   | Journal-level information                        |
| `journal.name`      | str    | Name of the journal                              |
| `journal.entry_count` | int  | Number of entries in the selection              |
| `journal.tags`      | list   | Tag frequency list: `[(tag_name, count), ...]`   |
| `entry`             | dict   | (Single-entry mode only) The current entry       |

#### Entry Variables (available on each item in `entries`)

| Variable          | Type      | Description                                     |
|-------------------|-----------|-------------------------------------------------|
| `entry.title`     | str       | Entry title (first line)                        |
| `entry.body`      | str       | Entry body text (everything after the title)    |
| `entry.date`      | datetime  | Entry date and time (use with `date` filter)    |
| `entry.tags`      | list[str] | List of tags in this entry (e.g., `["@work"]`)  |
| `entry.starred`   | bool      | Whether entry is starred                        |
| `entry.uuid`      | str       | Unique identifier (if available)                |
| `entry.fulltext`  | str       | Raw full entry text (if available)              |

#### Loop Variables (available inside `{% for %}`)

| Variable          | Type  | Description                                            |
|-------------------|-------|--------------------------------------------------------|
| `loop.index`      | int   | 1-based index of current iteration (1, 2, 3, ...)      |
| `loop.index0`     | int   | 0-based index of current iteration (0, 1, 2, ...)      |
| `loop.first`      | bool  | `True` on first iteration                              |
| `loop.last`       | bool  | `True` on last iteration                               |
| `loop.length`     | int   | Total number of items in the loop                      |

### Complete Filter Reference

| Filter Name | Arguments                      | Description & Example                                                 |
|-------------|--------------------------------|-----------------------------------------------------------------------|
| `date`      | `format_string` (str)         | Format a datetime using Python `strftime()` codes.<br>`{{ entry.date \| date:"%Y-%m-%d %H:%M" }}` → `2024-06-01 14:30` |
| `truncate`  | `length` (int), `suffix` (str, optional) | Truncate text to N chars, appending suffix if needed.<br>`{{ body \| truncate:100,"..." }}` |
| `join`      | `separator` (str)             | Join a list into a string with separator.<br>`{{ entry.tags \| join:", " }}` → `@work, @home` |
| `firstline` | none                           | Extract only the first line of text.<br>`{{ entry.body \| firstline }}` |
| `length`    | none                           | Get length/count of string or list.<br>`{{ entry.tags \| length }}` → `3` |
| `upper`     | none                           | Convert to UPPERCASE.<br>`{{ title \| upper }}` |
| `lower`     | none                           | Convert to lowercase.<br>`{{ title \| lower }}` |
| `strip`     | none                           | Remove leading/trailing whitespace.<br>`{{ title \| strip }}` |

Common Python `strftime()` date format codes:

| Code | Meaning                  | Example |
|------|--------------------------|---------|
| `%Y` | 4-digit year             | `2024`  |
| `%m` | 2-digit month (01-12)    | `06`    |
| `%d` | 2-digit day (01-31)      | `15`    |
| `%H` | 24-hour hour (00-23)     | `14`    |
| `%M` | Minute (00-59)           | `30`    |
| `%B` | Full month name          | `June`  |
| `%A` | Full weekday name        | `Monday`|
| `%I` | 12-hour hour (01-12)     | `02`    |
| `%p` | AM/PM indicator          | `PM`    |

### Complete Examples

#### Example 1: Simple Markdown List
```jinja
---
extension: md
name: Simple Markdown List
---
# My Journal

{% for entry in entries %}
## {{ entry.date | date:"%Y-%m-%d" }} - {{ entry.title }}{% if entry.starred %} ⭐{% endif %}

{% if entry.tags %}*Tags: {{ entry.tags | join:", " }}*{% endif %}

{{ entry.body }}

{% endfor %}
```

#### Example 2: HTML Report with Tag Cloud
```jinja
---
extension: html
name: Tag Cloud Report
---
<html>
<head>
    <title>Journal Report - {{ journal.entry_count }} entries</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 2em auto; }
        .entry { border: 1px solid #ccc; padding: 1em; margin: 1em 0; border-radius: 8px; }
        .tag { background: #3498db; color: white; padding: 2px 8px; border-radius: 10px; margin-right: 4px; }
        h2 { color: #2c3e50; }
    </style>
</head>
<body>
    <h1>📓 Journal Report</h1>
    <p>Total entries: <strong>{{ journal.entry_count }}</strong></p>

    <h2>🏷️ Tag Cloud</h2>
    <p>
    {% for tag, count in journal.tags %}
        <span class="tag">{{ tag }} ({{ count }})</span>
    {% endfor %}
    </p>

    <h2>📝 Entries</h2>
    {% for entry in entries %}
    <div class="entry">
        <h3>{{ entry.date | date:"%B %d, %Y" }} - {{ entry.title }}{% if entry.starred %} ⭐{% endif %}</h3>
        {% if entry.tags %}
            {% for tag in entry.tags %}
                <span class="tag">{{ tag }}</span>
            {% endfor %}
        {% endif %}
        <p>{{ entry.body | firstline }}</p>
    </div>
    {% endfor %}
</body>
</html>
```

#### Example 3: CSV-style Export
```jinja
---
extension: csv
name: CSV Export
---
"Date","Title","Tags","Starred","Body_Preview"
{% for entry in entries %}"{{ entry.date | date:"%Y-%m-%d" }}","{{ entry.title | strip }}","{{ entry.tags | join:";" }}",{{ entry.starred }},"{{ entry.body[:80] | truncate:80 | strip }}"{% endfor %}
```

#### Example 4: Summary with Sentiment Keywords
```jinja
---
extension: txt
name: Weekly Summary
---
═════════════════════════════════════════
       WEEKLY JOURNAL SUMMARY
       {{ journal.entry_count }} entries
═════════════════════════════════════════

Entries by date:
{% for entry in entries %}
  [{{ entry.date | date:"%a %m/%d" }}] {{ entry.title }}
  Tags: {{ entry.tags | join:", " }}
  Preview: {{ entry.body | firstline }}
{% endfor %}

─────────────────────────────────────────
Tag frequency:
{% for tag, count in journal.tags %}  {{ tag }}: {{ count }}
{% endfor %}
```

### Troubleshooting Template Errors

When there is an error in your template, `jrnl` will show a friendly message with:
- The error type and description
- The template file name
- The **exact line number** where the problem occurred
- The content of that line
- A helpful hint on how to fix it

#### Common Errors:

**"Unclosed 'for' block - expected 'endfor'"**
```
⚠️  模板语法错误: 未关闭的 'for' 块
   模板文件: my_template.template
   第 5 行: {% for entry in entries %}
   缺少对应的 '{% endfor %}' 标签
```
→ Fix: Add a `{% endfor %}` at the end of your loop.

**"Unknown filter 'capitalize'"**
```
⚠️  模板语法错误: 未知的过滤器 'capitalize'
   模板文件: report.template
   第 12 行: {{ entry.title | capitalize }}
   可用过滤器: date, firstline, join, length, lower, strip, truncate, upper
```
→ Fix: Check the spelling or use an available filter from the list.

**"Cannot resolve expression 'entry.wrong_field'"**
```
⚠️  模板语法错误: 无法解析表达式 'entry.wrong_field'
   模板文件: my_template.template
   第 8 行: {{ entry.wrong_field }}
   可用的顶层变量: entries, journal, entry, (entry attributes)
```
→ Fix: Use the correct attribute name (see "Available Variables" above).

## Report formats
Since formats use your journal data and display it in different ways, they can also be
used to create reports.

### Tags

``` sh
jrnl --format tags
# or
jrnl --tags
```

This format is a simple example of how formats can be used to create reports. It
displays each tag, and a count of how many entries in which tag appears in your journal
(or in the search results), sorted by most frequent.

Example output:
``` sh
@one                 : 32
@two                 : 17
@three               : 4
```

## Options

### Exporting with `--file`

Example: `jrnl --format json --file /some/path/to/a/file.txt`

By default, `jrnl` will output entries to your terminal. But if you provide `--file`
along with a filename, the same output that would have been to your terminal will be
written to the file instead. This is the same as piping the output to a file.

So, in bash for example, the following two statements are equivalent:

``` sh
jrnl --format json --file myjournal.json
```

``` sh
jrnl --format json > myjournal.json
```

#### Exporting to directories

If the `--file` argument is a directory, jrnl will export each entry into an individual file:

``` sh
jrnl --format yaml --file my_entries/
```

The contents of `my_entries/` will then look like this:

``` output
my_entries/
|- 2013_06_03_a-beautiful-day.yaml
|- 2013_06_07_dinner-with-gabriel.yaml
|- ...
```
