# Blogging for Logging

Source for <https://www.bloggingforlogging.com>, migrated from WordPress to Jekyll on GitHub Pages.

- Posts live in `_posts/` as Markdown. Each has an explicit `permalink` matching its original WordPress URL.
- Images live in `assets/images/YYYY/MM/`, mirroring the old `wp-content/uploads` layout.
- Posts containing Jinja `{{ }}` syntax are wrapped in `{% raw %}` so Liquid leaves them alone.

## Writing a new post

Create `_posts/YYYY-MM-DD-slug.md`:

```markdown
---
layout: post
title: "My post"
date: 2026-10-07 12:00:00 +0000
categories: ["windows"]
---

Content here.
```

## Building locally

```bash
podman run --rm -it -v "$PWD:/srv/jekyll:Z" -p 4000:4000 docker.io/jekyll/jekyll:4 jekyll serve
```

Or with Ruby installed: `bundle install && bundle exec jekyll serve`.

## WordPress backup

`wordpress-export/` holds the raw WordPress REST API dump (posts, pages, categories, tags, media metadata) and the `convert.py` script used to generate this site from it:

```bash
python3 wordpress-export/convert.py wordpress-export .
```
