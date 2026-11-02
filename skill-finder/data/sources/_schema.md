# Source file schema

Each `*.json` file in this directory is a curated knowledge source about skills.
Files whose names start with `_` (like this one) are ignored by the loader.
Sources are read in sorted filename order.

## Fields

Required:

- `source` (string, `^[a-z0-9-]+$`) - unique source id.
- `label` (string) - human-readable name.
- `skills` (list) - each item requires:
  - `slug` (string, `^[a-z0-9][a-z0-9-]*$`) - the **installed directory name**, never a guide's display slug.
  - `summary` (string).

Optional:

- `homepage` (string) - URL.
- `install` (string) - install command template; placeholders `{slug}` and `{agent}`.
- `install_all` (string) - install-everything command (no placeholders needed).
- `categories` (list of strings).
- per skill: `name` (string), `guide_slug` (string, display slug used by guides), `category` (string), `use_when` (string), `aliases` (list of strings).
- `journeys` (list) - each requires `slug` (string), `name` (string), `skills` (list of slugs); optional `tagline`, `phases` (int), `fits`.
- `routes` (list) - each requires `name` (string) and `steps` (list of `[slug, text]` pairs); optional `shortcut`, `note`.

## Placeholders

`{slug}` is replaced by the skill's installed `slug`; `{agent}` by the target agent,
exactly `claude-code` or `codex`.

## Merge rule

When several sources describe the same skill: earlier filename wins per field; both source names recorded.

## Example

```json
{
  "source": "wondel",
  "label": "Wondel.ai skills",
  "homepage": "https://skills.wondel.ai/skills",
  "install": "npx skills add wondelai/skills -s {slug} -g -a {agent}",
  "install_all": "npx skills add wondelai/skills --all --global",
  "categories": ["Design & UX", "Marketing & Messaging"],
  "skills": [
    {
      "name": "StoryBrand Messaging",
      "guide_slug": "storybrand",
      "slug": "storybrand-messaging",
      "category": "Marketing & Messaging",
      "summary": "Explain a product clearly by framing the customer as the main character and the company as a guide.",
      "use_when": "Use when the homepage talks about the company but visitors don't understand the benefit.",
      "aliases": ["storybrand", "story brand"]
    }
  ],
  "journeys": [
    {
      "slug": "create-website",
      "name": "Create a Website",
      "tagline": "Blank page → clear, designed, conversion-focused website",
      "phases": 10,
      "skills": ["one-page-marketing", "storybrand-messaging"],
      "fits": "new marketing site or landing page from scratch"
    }
  ],
  "routes": [
    {
      "name": "Improve an online shop with abandoned checkout",
      "steps": [["cro-methodology", "locate the drop-off"], ["ux-heuristics", "remove checkout friction"]],
      "shortcut": "improve-website",
      "note": "use conversion-optimization for one funnel"
    }
  ]
}
```
